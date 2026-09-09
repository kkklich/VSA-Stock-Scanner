// Legal information — one page holding the three documents a public financial
// information site in Poland has to publish:
//
//   1. Zastrzeżenia prawne / legal disclaimer — what the ratings are and are
//      not. Covers what Regulation (EU) 2016/958 (the MAR delegated act on
//      investment recommendations) expects to be disclosed: who produced the
//      recommendation, the methodology, the meaning of the ratings and their
//      horizon, a risk warning, the data sources, conflicts of interest and
//      the dating of every rating.
//   2. Regulamin / terms of service — required by art. 8 of the Polish Act on
//      Providing Services by Electronic Means (UŚUDE).
//   3. Polityka prywatności / privacy policy — GDPR art. 13 information about
//      the only personal data the site touches (server logs) plus what the app
//      keeps in the browser's localStorage.
//
// The publisher block at the top is the art. 5 UŚUDE identification: name,
// contact email and — when filled in — a correspondence address. The address
// is deliberately an EMPTY translation key (`legal.publisher.address`): it is
// only rendered once a real value is put in `pl.json` / `en.json`, so the live
// site never shows a placeholder.
//
// All copy lives in the i18n files, so both languages stay in sync. Section
// bodies are looked up by key name from the lists below.

import {
  AlertTriangle,
  FileText,
  Lock,
  Mail,
  Scale,
  User,
  Globe,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

/** Sub-sections of each document, in display order (keys under `legal.<doc>`). */
const DISCLAIMER_ITEMS = [
  'what',
  'method',
  'meaning',
  'nature',
  'risk',
  'sources',
  'conflict',
  'dating',
] as const

const TERMS_ITEMS = [
  'scope',
  'service',
  'requirements',
  'rules',
  'availability',
  'liability',
  'complaints',
  'changes',
] as const

const PRIVACY_ITEMS = [
  'controller',
  'scope',
  'purpose',
  'retention',
  'recipients',
  'storage',
  'rights',
  'external',
] as const

const DOCUMENTS = [
  { id: 'disclaimer', icon: AlertTriangle, items: DISCLAIMER_ITEMS },
  { id: 'terms', icon: FileText, items: TERMS_ITEMS },
  { id: 'privacy', icon: Lock, items: PRIVACY_ITEMS },
] as const

/** One labelled row of the publisher card. */
function PublisherRow({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof User
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon size={15} className="mt-0.5 shrink-0 text-slate-500" />
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wider text-slate-500">
          {label}
        </div>
        <div className="text-sm text-slate-200">{children}</div>
      </div>
    </div>
  )
}

export function LegalPage() {
  const { t } = useTranslation()

  const email = t('legal.publisher.email')
  // Empty by default — see the file header.
  const address = t('legal.publisher.address')

  return (
    <div className="flex max-w-4xl flex-col gap-6 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-start gap-3 border-b border-slate-800 pb-6">
        <Scale size={28} className="mt-0.5 shrink-0 text-emerald-500" />
        <div>
          <h1 className="text-2xl font-bold text-slate-100">
            {t('legal.pageTitle')}
          </h1>
          <p className="mt-1 text-sm leading-relaxed text-slate-400">
            {t('legal.intro')}
          </p>
        </div>
      </div>

      {/* Publisher — art. 5 UŚUDE identification data. */}
      <section
        aria-labelledby="legal-publisher"
        className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 sm:p-5"
      >
        <h2
          id="legal-publisher"
          className="text-[11px] font-semibold uppercase tracking-wider text-slate-400"
        >
          {t('legal.publisher.title')}
        </h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <PublisherRow icon={User} label={t('legal.publisher.nameLabel')}>
            {t('legal.publisher.name')}
          </PublisherRow>
          <PublisherRow icon={Mail} label={t('legal.publisher.emailLabel')}>
            <a
              href={`mailto:${email}`}
              className="text-emerald-400 hover:text-emerald-300 hover:underline"
            >
              {email}
            </a>
          </PublisherRow>
          <PublisherRow icon={Globe} label={t('legal.publisher.siteLabel')}>
            {t('legal.publisher.site')}
          </PublisherRow>
          {address ? (
            <PublisherRow
              icon={FileText}
              label={t('legal.publisher.addressLabel')}
            >
              {address}
            </PublisherRow>
          ) : null}
        </div>
        <p className="mt-4 text-xs text-slate-500">{t('legal.updated')}</p>
      </section>

      {/* Quick navigation between the three documents */}
      <nav aria-label={t('legal.contents')} className="grid gap-2 sm:grid-cols-3">
        {DOCUMENTS.map(({ id, icon: Icon }) => (
          <a
            key={id}
            href={`#${id}`}
            className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm text-emerald-400 hover:bg-slate-800"
          >
            <Icon size={16} />
            {t(`legal.${id}.title`)}
          </a>
        ))}
      </nav>

      {/* The documents themselves */}
      <div className="space-y-10">
        {DOCUMENTS.map(({ id, icon: Icon, items }) => (
          <section key={id} id={id} className="scroll-mt-4 space-y-4">
            <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
              <Icon size={22} className="text-emerald-500" strokeWidth={1.5} />
              <h2 className="text-lg font-semibold text-slate-100">
                {t(`legal.${id}.title`)}
              </h2>
            </div>

            {items.map((item) => (
              <article key={item} className="space-y-1">
                <h3 className="text-sm font-semibold text-slate-200">
                  {t(`legal.${id}.${item}.heading`)}
                </h3>
                <p className="text-sm leading-relaxed text-slate-400">
                  {t(`legal.${id}.${item}.body`)}
                </p>
              </article>
            ))}
          </section>
        ))}
      </div>
    </div>
  )
}
