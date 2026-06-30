import { describe, it, expect } from 'vitest';
import { gradeFromCore } from './grade';

describe('gradeFromCore 경계', () => {
  it.each([
    [0.8, 'S'],
    [0.799, 'A'],
    [0.6, 'A'],
    [0.599, 'B'],
    [0.4, 'B'],
    [0.399, 'C'],
    [0.001, 'C'],
  ] as const)('core=%f → %s', (core, grade) => {
    expect(gradeFromCore(core)).toBe(grade);
  });
});
