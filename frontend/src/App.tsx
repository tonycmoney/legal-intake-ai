import { IntakePage } from './components/IntakePage'
import { StaffApp } from './components/StaffApp'

export default function App() {
  return window.location.pathname.startsWith('/staff') ? <StaffApp /> : <IntakePage />
}
