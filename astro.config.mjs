// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

import cloudflare from '@astrojs/cloudflare';
import sitemap from '@astrojs/sitemap';

// https://astro.build/config
export default defineConfig({
  site: 'https://my-ai-blog-9pe.pages.dev/',
  vite: {
    plugins: [tailwindcss()]
  },
  integrations: [sitemap()],
  adapter: cloudflare()
});