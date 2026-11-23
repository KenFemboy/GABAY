import { BrowserRouter } from 'react-router-dom'

import { AuthProvider } from '../auth/AuthContext'
import Routes from './Routes'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes />
      </AuthProvider>
    </BrowserRouter>
  )
}
