import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import {installAuthGuard,forgetIdentity} from './services/auth'
import './styles/tokens.css'
import './styles/base.css'
import './styles/pages.css'

installAuthGuard(router)
window.addEventListener('aq:unauthorized',()=>{forgetIdentity();void router.replace('/auth/login')})
createApp(App).use(createPinia()).use(router).mount('#app')
