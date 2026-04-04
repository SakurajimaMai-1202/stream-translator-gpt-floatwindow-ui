import { createRouter, createWebHistory } from 'vue-router';
import HomeView from '../views/HomeView.vue';
import SettingsView from '../views/SettingsView.vue';
import FloatingSubtitleView from '../views/FloatingSubtitleView.vue';
import SubtitleSettingsView from '../views/SubtitleSettingsView.vue';
import MobileSubtitleView from '../views/MobileSubtitleView.vue';
import DesktopSubtitleView from '../views/DesktopSubtitleView.vue';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView
    },
    {
      path: '/subtitle',
      name: 'subtitle',
      component: FloatingSubtitleView
    },
    {
      path: '/subtitle-settings',
      name: 'subtitle-settings',
      component: SubtitleSettingsView
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

export default router;
