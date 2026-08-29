export const APP_ENV = (process.env.NEXT_PUBLIC_APP_ENV || 'production').trim().toLowerCase()
export const IS_PRODUCTION_UI = APP_ENV === 'production'
export const SHOW_DIAGNOSTICS_UI = !IS_PRODUCTION_UI && (process.env.NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI || 'false').trim().toLowerCase() === 'true'
