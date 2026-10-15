import { createRouter, createWebHistory } from 'vue-router';
import HomeView from '../views/HomeView.vue';
import SettingsView from '../views/SettingsView.vue';
import FloatingSubtitleView from '../views/FloatingSubtitleView.vue';
import SubtitleSettingsView from '../views/SubtitleSettingsView.vue';
import MobileSubtitleView from '../views/MobileSubtitleView.vue';
import DesktopSubtitleView from '../views/DesktopSubtitleView.vue';
import MainLayout from '../components/MainLayout.vue';
import LocalTranslationView from '../views/LocalTranslationView.vue';
import GuideView from '../views/GuideView.vue';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'home',
          component: HomeView
        },
        {
          path: 'settings',
          name: 'settings',
          component: SettingsView
        },
        {
          path: 'subtitle-style',
          name: 'subtitle-style',
          component: SubtitleSettingsView
        },
        {
          path: 'local-translation',
          name: 'local-translation',
          component: LocalTranslationView
        },
        { path: 'llm-models', redirect: '/local-translation' },
        { path: 'translation-models', redirect: '/local-translation' },
        {
          path: 'guide',
          name: 'guide',
          component: GuideView
        }
      ]
    },
    {
      path: '/subtitle-settings',
      name: 'subtitle-settings',
      component: SubtitleSettingsView
    },
    {
      path: '/subtitle',
      name: 'subtitle',
      component: FloatingSubtitleView
    },
    {
      path: '/mobile',
      name: 'mobile-subtitle',
      component: MobileSubtitleView
    },
    {
      path: '/desktop',
      name: 'desktop-subtitle',
      component: DesktopSubtitleView
    }
  ]
});

router.beforeEach(to => {
  const tab = Array.isArray(to.query.tab) ? to.query.tab[0] : to.query.tab;
  if (to.path === '/settings' && tab === 'llama') return { path: '/local-translation', replace: true };
});

export default router;
