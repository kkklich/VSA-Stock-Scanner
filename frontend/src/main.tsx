import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import './i18n'
import App from './App.tsx'
import { initTheme } from './lib/theme'

// Load the saved light/dark choice before the first render. The inline script
// in index.html has already painted it; this hands the same state to React and
// starts listening for OS theme changes (for the "System" setting).
initTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
