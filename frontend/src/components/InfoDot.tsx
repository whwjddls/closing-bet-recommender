import { useId, useState } from 'react';

type Align = 'center' | 'left' | 'right';

// 재사용 용어 툴팁: 작은 `?` 버튼 + hover/focus 시 설명 팝오버.
// 접근성: 버튼 aria-label + 열릴 때 aria-describedby, 팝오버 role=tooltip.
export default function InfoDot({
  label,
  text,
  align = 'center',
}: {
  label: string;
  text: string;
  align?: Align;
}) {
  const [open, setOpen] = useState(false);
  const tipId = useId();

  return (
    <span className="info-dot-wrap">
      <button
        type="button"
        className="info-dot"
        data-testid="info-dot"
        aria-label={`${label} 설명`}
        aria-describedby={open ? tipId : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        ?
      </button>
      {open && (
        <span
          id={tipId}
          role="tooltip"
          data-testid="info-tip"
          className={`info-tip info-tip--${align}`}
        >
          {text}
        </span>
      )}
    </span>
  );
}
