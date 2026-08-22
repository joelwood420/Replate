import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IngredientRow } from './IngredientRow';
import { MethodStep } from './MethodStep';
import { ComponentCard } from './ComponentCard';

describe('IngredientRow', () => {
  it('renders the ingredient name and quantity', () => {
    render(<IngredientRow name="Butter" qty="2 tbsp" />);
    expect(screen.getByText('Butter')).toBeInTheDocument();
    expect(screen.getByText('2 tbsp')).toBeInTheDocument();
  });
});

describe('MethodStep', () => {
  it('renders the step number and instruction text', () => {
    render(<MethodStep number={3} text="Fold gently" />);
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Fold gently')).toBeInTheDocument();
  });
});

describe('ComponentCard', () => {
  it('renders name and role, and falls back to "Component" when role is null', () => {
    const { rerender } = render(<ComponentCard role="Sauce" name="Beurre blanc" />);
    expect(screen.getByText('Sauce')).toBeInTheDocument();
    expect(screen.getByText('Beurre blanc')).toBeInTheDocument();

    rerender(<ComponentCard role={null} name="Garnish" />);
    expect(screen.getByText('Component')).toBeInTheDocument();
  });

  it('reflects selection via aria-pressed and fires onClick', async () => {
    const onClick = vi.fn();
    render(<ComponentCard role="Base" name="Risotto" selected onClick={onClick} />);
    const button = screen.getByRole('button', { name: /Risotto/ });
    expect(button).toHaveAttribute('aria-pressed', 'true');

    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });
});
