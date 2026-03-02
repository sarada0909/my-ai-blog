import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';

export async function GET(context) {
    const blog = await getCollection('blog');
    return rss({
        title: 'AI News Bot',
        description: '최신 AI 뉴스와 기술 트렌드를 자동으로 분석하여 전해드리는 AI 블로그입니다.',
        site: context.site || 'https://my-ai-blog-9pe.pages.dev/',
        items: blog.map((post) => ({
            title: post.data.title,
            pubDate: post.data.pubDate,
            description: post.data.description,
            link: `/blog/${post.slug}/`,
        })),
        customData: `<language>ko-kr</language>`,
    });
}
