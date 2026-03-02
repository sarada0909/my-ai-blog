import { z, defineCollection } from 'astro:content';

const blogCollection = defineCollection({
  type: 'content', // v2.5+ content collection. v5.0 might prefer 'content' inside loader or similar, but for md files this basic schema works.
  schema: z.object({
    title: z.string(),
    pubDate: z.date().or(z.string().transform((str) => new Date(str))),
    description: z.string().optional(),
  }),
});

export const collections = {
  'blog': blogCollection,
};
