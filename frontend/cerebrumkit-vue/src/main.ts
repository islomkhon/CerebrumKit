import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import i18n from './plugins/i18n'
import { installDemoRuntime } from './demo'
import './style.css'

// A no-op unless the bundle was built with VITE_DEMO=1. It has to run before
// the app mounts: the router guard reads the session from local storage, and
// the panel opens a chat socket as soon as a chat is selected.
installDemoRuntime()

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.mount('#app')
