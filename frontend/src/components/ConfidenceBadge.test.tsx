import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ConfidenceBadge } from './ConfidenceBadge';

describe('ConfidenceBadge', () => {
  it('shows the cross-checked copy for a menu match', () => {
    render(<ConfidenceBadge matchMethod="menu_matched" />);
    expect(screen.getByText('Cross-checked with menu')).toBeInTheDocument();
  });

  it('shows an AI-estimate copy for the medium vision-only outcome', () => {
    render(<ConfidenceBadge matchMethod="vision_only_medium" />);
    expect(screen.getByText('AI estimate')).toBeInTheDocument();
  });

  it('shows the unmatched copy for the low vision-only outcome', () => {
    render(<ConfidenceBadge matchMethod="vision_only_low" />);
    expect(screen.getByText(/Unmatched/)).toBeInTheDocument();
  });
});
