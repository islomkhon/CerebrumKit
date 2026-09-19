import { createI18n } from 'vue-i18n'
import en from '../locales/en.json'
import ru from '../locales/ru.json'
import zh from '../locales/zh.json'
import es from '../locales/es.json'
import de from '../locales/de.json'
import fr from '../locales/fr.json'

type MessageSchema = typeof en

const i18n = createI18n<[MessageSchema], 'en' | 'ru' | 'zh' | 'es' | 'de' | 'fr'>({
  legacy: false,
  locale: localStorage.getItem('locale') || 'en',
  fallbackLocale: 'en',
  messages: { en, ru, zh, es, de, fr },
})

export default i18n
