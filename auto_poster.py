import os
import re
import datetime
from dotenv import load_dotenv
import feedparser
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv()

# Configure API Keys
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_KEY:
    print("Error: GEMINI_API_KEY is not set in the .env file.")
    exit(1)

genai.configure(api_key=GEMINI_KEY)

# We will use the standard Gemini model
model = genai.GenerativeModel('gemini-2.5-flash')

def fetch_rss_news():
    """Fetches recent AI news from RSS feeds."""
    print("Fetching news from RSS feeds...")
    
    # List of good AI / Tech news RSS feeds
    rss_urls = [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://raw.githubusercontent.com/rowancheung/ai-news-rss/main/ai-news.xml", # Example AI news
        "https://www.artificialintelligence-news.com/feed/"
    ]
    
    all_news_items = []
    
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            # Get top 5 recent entries from each feed
            for entry in feed.entries[:5]: 
                image_url = ""
                if "media_content" in entry and len(entry.media_content) > 0:
                    image_url = entry.media_content[0].get("url", "")
                elif "media_thumbnail" in entry and len(entry.media_thumbnail) > 0:
                    image_url = entry.media_thumbnail[0].get("url", "")
                    
                all_news_items.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", entry.get("description", "")),
                    "link": entry.get("link", ""),
                    "source": feed.feed.get("title", url),
                    "image": image_url
                })
        except Exception as e:
            print(f"Error parsing feed {url}: {e}")
            
    print(f"Successfully fetched {len(all_news_items)} news items.")
    return all_news_items

def generate_blog_post(news_item):
    """Uses Gemini to summarize a single news item into a blog post."""
    if not news_item:
        return None, None

    safe_title = news_item['title'].encode('ascii', 'ignore').decode('ascii')
    print(f"Generating blog post for: {safe_title}...")
    
    text = f"Title: {news_item['title']}\nSource: {news_item['source']}\nSummary: {news_item['summary']}\nLink: {news_item['link']}\nImage URL: {news_item.get('image', '')}"
    
    # Extract YouTube links before stripping HTML
    yt_links = re.findall(r'(https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https?://youtu\.be/[\w-]+|https?://(?:www\.)?youtube\.com/embed/[\w-]+)', text)
    unique_yt = list(set(yt_links))
    yt_text = "\nYouTube Links: " + ", ".join(unique_yt) if unique_yt else ""
    
    # Strip some HTML tags roughly but use space instead of empty to keep words separated
    text = re.sub('<[^<]+?>', ' ', text) 
    text += yt_text
    
    prompt = f"""
    You are a professional AI news blogger. Based on the following news article, write an engaging and informative news blog post in Korean.
    
    CRITICAL INSTRUCTIONS FOR MAXIMUM READABILITY:
    1. Base your article ONLY on the provided news item.
    2. Provide a catchy, click-worthy Korean title for the blog post on the VERY FIRST line. Do not use Markdown heading `#` for the title.
    3. Use appropriate emojis (🚀, 💡, 🌐, 📢, etc.) throughout the headings, bullet points, and text to make the post feel trendy and engaging.
    4. Right under the title, you MUST provide a "## 📌 요약" section. Write 3~4 bullet points summarizing the entire article. Do not use the word "3줄 요약", just use "## 📌 요약" so the heading is large.
    5. Cover Image: right after the 요약 section, if an "Image URL" is provided in the News Item below, include it as a Markdown image: `![기사 관련 이미지](the_provided_image_url)`. If NO image URL is provided, formulate a short English image prompt based on the article's topic, replace spaces with `%20`, and use this format exactly: `![AI 이미지](https://image.pollinations.ai/prompt/YOUR_PROMPT_HERE?width=800&height=400&nologo=true)`.
    6. You MUST use Markdown headings (`##`, `###`) to structure the rest of the body into logical sections.
    7. Heavy structure: Avoid long paragraphs. Break almost everything down into bullet points (`*` or `-`).
    8. Highlight key terms: You MUST bold (`**text**`) important keywords, names, numbers, and concepts so the reader can easily scan the document.
    9. You MUST use generous line breaks (empty lines) between sections and lists.
    10. The tone should be professional, objective, and clear.
    11. YouTube Videos: If any "YouTube Links" are provided in the News Item below, you MUST embed them prominently in the post using this format: `[▶️ 관련 유튜브 영상 보기](YOUTUBE_LINK_HERE)`.
    12. At the very end of the post, you MUST include a "출처" (Source) section separated by a horizontal rule (`---`), formatted exactly like this:
       
       ---
       ### 출처
       * **원문 제목:** [English Title]
       * **출처:** [Source Name]
       * [원문 기사 보기](the_link_here)
    
    News Item:
    {text}
    """
    
    try:
        response = model.generate_content(prompt)
        content = response.text
        
        # Extract title (assume first non-empty line is the title)
        lines = [line.strip() for line in content.strip().split('\n') if line.strip()]
        title = lines[0].replace("#", "").strip() if lines else "오늘의 AI 뉴스"
        
        # Remove the title from the body to avoid duplication
        body = "\n".join(lines[1:])
        
        return title, body
    except Exception as e:
        print(f"Error generating content: {e}")
        return None, None

def save_blog_post(title, content):
    """Saves the generated content as a Markdown file in the Astro blog directory."""
    if not title or not content:
        print("No content to save.")
        return

    # Clean the title to make a valid filename
    clean_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-')
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    # Add a timestamp to the filename to avoid overwriting multiple posts on the same day
    timestamp = datetime.datetime.now().strftime("%H%M%S")
    filename = f"{today}-{timestamp}-{clean_title[:30]}.md"
    
    # Ensure correct path to Astro blog content directory
    filepath = os.path.join(os.path.dirname(__file__), "src", "content", "blog", filename)
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # Escape quotes for YAML frontmatter
    yaml_safe_title = title.replace('"', '\\"')
    
    # Construct Astro frontmatter
    md_content = f"""---
title: "{yaml_safe_title}"
pubDate: "{datetime.datetime.now().isoformat()}"
description: "{yaml_safe_title}에 대한 AI 요약 뉴스입니다."
---

{content}
"""

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Successfully saved blog post to: {filepath}")
    except Exception as e:
        print(f"Error saving file: {e}")

def main():
    print("Starting AI News Bot...")
    news_items = fetch_rss_news()
    
    if news_items:
        # Generate and save a separate post for each of the top items
        # Generate 5 posts again using the new model constraint
        for item in news_items[:5]:
            title, content = generate_blog_post(item)
            if title and content:
                save_blog_post(title, content)
            else:
                safe_title = item['title'].encode('ascii', 'ignore').decode('ascii')
                print(f"Failed to generate post for: {safe_title}")
        print("Bot finished successfully.")
    else:
        print("No news found. Exiting.")

if __name__ == "__main__":
    main()
