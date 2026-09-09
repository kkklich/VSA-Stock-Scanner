// Site footer — rendered at the end of every page's scrollable content.
//
// It carries the two things that must be reachable from anywhere on a public
// financial-information site: the short "this is not investment advice"
// disclaimer, and the publisher's contact data + a link to the full legal
// documents (art. 5 UŚUDE identification, MAR/2016/958 risk warning).
// The long-form versions live on /legal (see LegalPage).

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

export function Footer() {
  const { t } = useTranslation()
  const email = t('legal.publisher.email')

  return (
    <footer className="mt-8 border-t border-slate-800 px-4 py-6 text-xs leading-relaxed text-slate-500 sm:px-6">
      <div className="mx-auto flex max-w-5xl flex-col gap-3">
        <p>{t('legal.footerNote')}</p>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <Link
            to="/legal"
            className="text-slate-400 underline-offset-2 hover:text-emerald-400 hover:underline"
          >
            {t('legal.footerLink')}
          </Link>
          <span className="text-slate-600">·</span>
          <span>
            {t('legal.publisher.name')} —{' '}
            <a
              href={`mailto:${email}`}
              className="underline-offset-2 hover:text-emerald-400 hover:underline"
            >
              {email}
            </a>
          </span>
          <span className="ml-auto text-slate-600">
            © {new Date().getFullYear()} {t('common.appName')}
          </span>
        </div>
      </div>
    </footer>
  )
}
