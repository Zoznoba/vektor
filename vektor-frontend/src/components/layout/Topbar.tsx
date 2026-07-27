import logo from '../../assets/logo-dark.png';
import { Avatar } from '../ui/Avatar';
import './Topbar.css';

interface TopbarProps {
  userFullName: string;
  userRoleLabel: string;
  onLogout?: () => void;
}

export function Topbar({ userFullName, userRoleLabel, onLogout }: TopbarProps) {
  return (
    <header className="app-topbar">
      <div className="app-topbar__brand">
        <img src={logo} alt="Школа Вектор" />
      </div>

      <div className="app-topbar__user">
        <div className="app-topbar__who">
          <div className="app-topbar__who-name">{userFullName}</div>
          <div className="app-topbar__who-role">{userRoleLabel}</div>
        </div>
        <Avatar fullName={userFullName} />
        {onLogout && (
          <button className="app-topbar__logout" onClick={onLogout} title="Выйти">
            Выйти
          </button>
        )}
      </div>
    </header>
  );
}
