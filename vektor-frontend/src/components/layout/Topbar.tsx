import logo from '../../assets/logo.jpg';
import { Avatar } from '../ui/Avatar';
import './Topbar.css';

interface TopbarProps {
  userFullName: string;
  userRoleLabel: string;
}

export function Topbar({ userFullName, userRoleLabel }: TopbarProps) {
  return (
    <header className="app-topbar">
      <div className="app-topbar__brand">
        <img src={logo} alt="Вектор" />
        <div>
          <div className="app-topbar__name">Вектор</div>
          <div className="app-topbar__role">платформа</div>
        </div>
      </div>

      <div className="app-topbar__user">
        <div className="app-topbar__who">
          <div className="app-topbar__who-name">{userFullName}</div>
          <div className="app-topbar__who-role">{userRoleLabel}</div>
        </div>
        <Avatar fullName={userFullName} />
      </div>
    </header>
  );
}
