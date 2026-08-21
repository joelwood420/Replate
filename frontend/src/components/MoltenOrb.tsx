import { useEffect, useRef } from 'react';

/**
 * The molten-gold core of the ProcessingOrb: a live WebGL fragment shader that renders a
 * folding pool of caustic gold — a sauce reducing in a hot pan — inside the orb's ring.
 *
 * This is purely additive craft: the surrounding CSS orb (track ring, comet arc, pulsing
 * dot, glyph) is the complete, shippable experience on its own. This canvas only mounts when
 * WebGL is available and the user hasn't asked to reduce motion (both gated by the parent),
 * so a failed context or a locked-down device silently falls back to the flat orb — the
 * design system's rule that the orb is the one sanctioned bloom of light still holds either
 * way.
 *
 * `intensity` (0 identify → 1 generate) and `warm` ramp smoothly in the render loop rather
 * than snapping, so the slow "reverse-engineer" stage visibly deepens the churn instead of
 * cutting to it. Rendering pauses when the tab is hidden.
 */

const VERT = `
attribute vec2 a_pos;
varying vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;

// Domain-warped value-noise fBm → molten caustic filaments, top-lit into a spherical pool,
// coloured across dark amber → candlelit gold → a cream-gold highlight. Kept deliberately
// restrained (dark base, bright only in the veins) so the pool reads as intimate candlelight,
// not a lava lamp — ≤10% of it ever reaches full gold, per the Single Flame rule.
const FRAG = `
precision highp float;
varying vec2 v_uv;
uniform float u_time;
uniform float u_intensity;
uniform float u_warm;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 345.45));
  p += dot(p, p + 34.345);
  return fract(p.x * p.y);
}
float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}
float fbm(vec2 p) {
  float v = 0.0;
  float amp = 0.5;
  for (int i = 0; i < 5; i++) {
    v += amp * noise(p);
    p *= 2.0;
    amp *= 0.5;
  }
  return v;
}

void main() {
  vec2 p = v_uv * 2.0 - 1.0;      // -1..1
  float r = length(p);
  float disc = smoothstep(1.0, 0.84, r);
  if (disc <= 0.001) discard;

  float t = u_time;

  // Two-level domain warp: fold the noise field through itself so the veins swirl and
  // reconnect like molten metal rather than scrolling flatly.
  vec2 q = vec2(
    fbm(p * 1.6 + vec2(0.0, t * 0.12)),
    fbm(p * 1.6 + vec2(3.2, -t * 0.10))
  );
  vec2 s = vec2(
    fbm(p * 2.2 + q * 1.8 + vec2(1.7, t * 0.15)),
    fbm(p * 2.2 + q * 1.8 + vec2(-2.3, t * 0.13))
  );
  float n = fbm(p * 2.0 + s * 2.2 + t * 0.05);

  // Sharpen into caustic veins, plus a filament riding the mid band. Kept restrained so the
  // bright vein is a thread through the pool, not a wash across it.
  float caustic = pow(n, 2.0);
  caustic += 0.22 * pow(max(0.0, 1.0 - abs(n - 0.62) * 3.2), 3.0);

  // Top-lit spherical shading: brighter toward the upper centre, matching the app's 155deg
  // top-light, so the disc reads as a pool with volume, not flat noise.
  float topLight = clamp(0.6 + p.y * 0.5, 0.0, 1.2);
  float b = caustic * (0.55 + 0.5 * topLight);

  // The pool sits mostly in dim amber; the bright gold lives in the veins, and intensity
  // lifts them toward the generate stage — where the hot-white filaments start to appear.
  // Tuned so only the veins (≤10% of the disc) ever reach full gold: the Single Flame rule.
  float glow = clamp(b * (1.25 + 0.5 * u_intensity), 0.0, 1.15);

  vec3 deep = vec3(0.10, 0.05, 0.016);
  vec3 mid  = vec3(0.62, 0.42, 0.16) + u_warm * vec3(0.05, 0.02, -0.02);
  vec3 hot  = vec3(0.92, 0.74, 0.42) + u_warm * vec3(0.04, 0.0, -0.05);

  vec3 col = mix(deep, mid, smoothstep(0.26, 0.7, glow));
  col = mix(col, hot, smoothstep(0.8, 1.05, glow));

  // Darken the rim so the pool sits within the ring, and gather the very centre down a
  // little so the serif glyph reads as branded into the hot gold rather than lost in it.
  float rim = smoothstep(1.0, 0.18, r);
  col *= mix(0.22, 1.0, rim);
  col *= mix(0.62, 1.0, smoothstep(0.0, 0.5, r));

  gl_FragColor = vec4(col, disc);
}`;

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader | null {
  const sh = gl.createShader(type);
  if (!sh) return null;
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    gl.deleteShader(sh);
    return null;
  }
  return sh;
}

export function MoltenOrb({
  className,
  intensity,
  warm,
}: {
  className?: string;
  intensity: number;
  warm: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Live targets read by the render loop, so a stage change doesn't re-init the context.
  const targetRef = useRef({ intensity, warm });
  targetRef.current = { intensity, warm };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = (canvas.getContext('webgl', { alpha: true, premultipliedAlpha: false, antialias: true }) ||
      canvas.getContext('experimental-webgl', { alpha: true })) as WebGLRenderingContext | null;
    if (!gl) return; // No WebGL → the CSS orb underneath is the fallback.

    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;
    const prog = gl.createProgram();
    if (!prog) return;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'a_pos');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    const uTime = gl.getUniformLocation(prog, 'u_time');
    const uIntensity = gl.getUniformLocation(prog, 'u_intensity');
    const uWarm = gl.getUniformLocation(prog, 'u_warm');

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      const size = canvas.clientWidth || 90;
      const px = Math.round(size * dpr);
      if (canvas.width !== px) {
        canvas.width = px;
        canvas.height = px;
        gl.viewport(0, 0, px, px);
      }
    };
    resize();

    let raf = 0;
    let running = true;
    const start = performance.now();
    // Eased current values, lerped toward the target each frame for a smooth stage ramp.
    let curI = targetRef.current.intensity;
    let curW = targetRef.current.warm;

    const render = (now: number) => {
      if (!running) return;
      resize();
      const t = (now - start) / 1000;
      const tgt = targetRef.current;
      // Churn faster as intensity climbs, so generate churns harder than identify.
      curI += (tgt.intensity - curI) * 0.03;
      curW += (tgt.warm - curW) * 0.03;
      const churn = 0.6 + curI * 0.7;
      gl.uniform1f(uTime, t * churn);
      gl.uniform1f(uIntensity, curI);
      gl.uniform1f(uWarm, curW);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      raf = requestAnimationFrame(render);
    };
    raf = requestAnimationFrame(render);

    const onVisibility = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (!running) {
        running = true;
        raf = requestAnimationFrame(render);
      }
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      document.removeEventListener('visibilitychange', onVisibility);
      // Deliberately do NOT loseContext() here. A <canvas> element vends exactly one WebGL
      // context for its lifetime; releasing it means React 18 StrictMode's throwaway
      // remount (mount → cleanup → mount) gets a dead context back and the shader never
      // draws. Stopping the render loop is enough; the GPU context is freed when the canvas
      // element is removed and garbage-collected on real unmount.
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
