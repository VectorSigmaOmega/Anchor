// Every icon in Anchor is inline SVG written for this design: stroke-based,
// `currentColor`, round caps and joins. There is deliberately no icon library —
// the marks share one construction so they sit together at small sizes.

type IconProps = {
  size?: number;
  className?: string;
};

function Icon({
  size = 16,
  className,
  strokeWidth = 2,
  fill = "none",
  children,
}: IconProps & {
  strokeWidth?: number;
  fill?: string;
  children: React.ReactNode;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/** The brand mark. Drawn on a 24×26 box, so height tracks width at 26/24. */
export function AnchorMark({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={Math.round((size * 26) / 24)}
      viewBox="0 0 24 26"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="4" r="2.4" />
      <line x1="12" y1="6.4" x2="12" y2="22" />
      <line x1="7" y1="11" x2="17" y2="11" />
      <path d="M4 15c0 5 3.6 7.6 8 7.6s8-2.6 8-7.6" />
    </svg>
  );
}

export function ArrowRight(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M5 12h13M12 5l7 7-7 7" />
    </Icon>
  );
}

export function ArrowUp(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={2.2}>
      <path d="M12 19V5M5 12l7-7 7 7" />
    </Icon>
  );
}

export function ArrowUpRight(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M7 17L17 7M8 7h9v9" />
    </Icon>
  );
}

export function ChevronDown(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 9l6 6 6-6" />
    </Icon>
  );
}

export function Plus(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  );
}

export function Trash(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.8}>
      <path d="M4 7h16M10 7V5h4v2M6 7l1 12h10l1-12" />
    </Icon>
  );
}

export function Sun(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.8}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
    </Icon>
  );
}

export function Moon(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.8}>
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5z" />
    </Icon>
  );
}

export function Copy(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.8}>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h8" />
    </Icon>
  );
}

export function Check(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M20 6L9 17l-5-5" />
    </Icon>
  );
}

export function Retry(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.8}>
      <path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v4h-4" />
    </Icon>
  );
}

export function ThumbUp({ filled, ...props }: IconProps & { filled?: boolean }) {
  return (
    <Icon {...props} strokeWidth={1.8} fill={filled ? "currentColor" : "none"}>
      <path d="M7 22V10l4.5-8A2.5 2.5 0 0 1 14 5v4h4.5a2 2 0 0 1 2 2.4l-1.6 8A2 2 0 0 1 17 21H7z" />
    </Icon>
  );
}

export function ThumbDown({
  filled,
  ...props
}: IconProps & { filled?: boolean }) {
  return (
    <Icon {...props} strokeWidth={1.8} fill={filled ? "currentColor" : "none"}>
      <path d="M17 2v12l-4.5 8A2.5 2.5 0 0 1 10 19v-4H5.5a2 2 0 0 1-2-2.4l1.6-8A2 2 0 0 1 7 3h10z" />
    </Icon>
  );
}

export function Stop(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.8} fill="currentColor">
      <rect x="7" y="7" width="10" height="10" rx="1.5" />
    </Icon>
  );
}

/** Landing benefit marks — drawn a touch lighter, at 1.7, because they run at 20px. */
export function DocumentMark(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.7}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </Icon>
  );
}

export function MagnifierPlus(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.7}>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5M8 11h6M11 8v6" />
    </Icon>
  );
}

export function ShieldCheck(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.7}>
      <path d="M12 3l7 3v6c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6z" />
      <path d="M9 12l2 2 4-4" />
    </Icon>
  );
}

export function CircleSlash(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.7}>
      <circle cx="12" cy="12" r="9" />
      <path d="M6 18L18 6" />
    </Icon>
  );
}

/** Drawer controls. Not in the prototype, which is desktop-only. */
export function Menu(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.8}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Icon>
  );
}

export function Close(props: IconProps) {
  return (
    <Icon {...props} strokeWidth={1.8}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Icon>
  );
}
