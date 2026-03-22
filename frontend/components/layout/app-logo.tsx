interface AppLogoProps {
  className?: string;
}

export function AppLogo({ className }: AppLogoProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 64 64"
      role="img"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="6" y="6" width="52" height="52" rx="14" className="app-logo-frame" />
      <path d="M18 43h8V23h20v-7H18z" className="app-logo-f" />
      <path d="M34 28h12v7H34z" className="app-logo-t-top" />
      <path d="M39 28h7v21h-7z" className="app-logo-t-stem" />
      <circle cx="50" cy="16" r="3" className="app-logo-dot" />
    </svg>
  );
}