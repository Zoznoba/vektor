import './Avatar.css';

interface AvatarProps {
  /** Имя и фамилия — инициалы берутся автоматически */
  fullName: string;
  className?: string;
}

export function Avatar({ fullName, className = '' }: AvatarProps) {
  const initials = fullName
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');

  return (
    <div className={`avatar ${className}`.trim()} title={fullName}>
      {initials}
    </div>
  );
}
