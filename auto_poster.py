import os
import re
import datetime
from dotenv import load_dotenv
import feedparser
import google.generativeai as genai
import urllib.parse
import time

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
        "https://www.theverge.com/rss/artificial-intelligence/index.xml", # The Verge AI
        "https://venturebeat.com/category/ai/feed/" # VentureBeat AI
    ]
    
    all_news_items = []
    
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            # Get top 10 recent entries from each feed to ensure we have enough
            for entry in feed.entries[:10]: 
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
    3. On the SECOND line, write a 1-sentence description summarizing the article. Start this line with 'Description: '.
    4. Use appropriate emojis (🚀, 💡, 🌐, 📢, etc.) throughout the headings, bullet points, and text to make the post feel trendy and engaging.
    5. Right after the description, you MUST provide a "## 📌 요약" section. Write 3~4 bullet points summarizing the entire article.
    6. Include the following image placeholder exactly as it is right after the 요약 section:
       [IMAGE_PLACEHOLDER]
    7. You MUST use Markdown headings (`##`, `###`) to structure the rest of the body into logical sections.
    8. Heavy structure: Avoid long paragraphs. Break almost everything down into bullet points (`*` or `-`).
    9. Highlight key terms: You MUST bold (`**text**`) important keywords, names, numbers, and concepts so the reader can easily scan the document.
    10. You MUST use generous line breaks (empty lines) between sections and lists.
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
        
        # Extract title and description
        lines = [line.strip() for line in content.strip().split('\n') if line.strip()]
        title = lines[0].replace("#", "").strip() if lines else "오늘의 AI 뉴스"
        
        description = f"{title}에 대한 AI 요약 뉴스입니다."
        body_start_idx = 1
        
        if len(lines) > 1 and lines[1].startswith("Description:"):
            description = lines[1].replace("Description:", "").strip()
            body_start_idx = 2
            
        body = "\n".join(lines[body_start_idx:])
        
        # Replace image placeholder
        image_url = news_item.get('image', '')
        if image_url:
            image_markdown = f"![기사 관련 이미지]({image_url})"
        else:
            # pollinations.ai is currently returning Error 1033. Using a reliable Unsplash Source placeholder.
            # Extract taking the first significant word from the title for a better Unsplash search
            import string
            words = [w.strip(string.punctuation) for w in news_item['title'].split() if len(w) > 3]
            keyword = words[0] if words else "technology"
            safe_keyword = urllib.parse.quote(keyword)
            # Unsplash Source API format: https://source.unsplash.com/{width}x{height}/?{keyword},{keyword}
            image_markdown = f"![AI 관련 이미지](https://source.unsplash.com/800x400/?artificial,intelligence,{safe_keyword})"
            
        body = body.replace("[IMAGE_PLACEHOLDER]", image_markdown)
        
        return title, description, body
    except Exception as e:
        print(f"Error generating content (falling back to RSS data): {e}")
        # Fallback to pure RSS data when Gemini API hits a rate limit
        title = f"[속보] {news_item['title']}"
        description = news_item.get('summary', '')[:100] + "..." if news_item.get('summary') else f"{title}에 대한 소식입니다."
        
        # Build a basic fallback body
        image_url = news_item.get('image', '')
        if image_url:
            image_markdown = f"![기사 관련 이미지]({image_url})"
        else:
            import string
            words = [w.strip(string.punctuation) for w in news_item['title'].split() if len(w) > 3]
            keyword = words[0] if words else "technology"
            safe_keyword = urllib.parse.quote(keyword)
            image_markdown = f"![AI 관련 이미지](https://source.unsplash.com/800x400/?artificial,intelligence,{safe_keyword})"
            
        body = f"""
## 📌 요약
* 기사 원문 요약 내용입니다.
* {description}
* 자세한 내용은 아래 원문을 참고해 주세요.

{image_markdown}

## 🚀 상세 내용
이 기사는 외부 통신 문제로 자동 요약이 지연되어 원문 데이터를 직접 노출합니다.

{news_item.get('summary', '조금 더 상세한 정보를 원하시면 원문을 확인해주세요.')}

---
### 출처
* **원문 제목:** {news_item['title']}
* **출처:** {news_item['source']}
* [원문 기사 보기]({news_item['link']})
"""
        return title, description, body

def save_blog_post(title, description, content):
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
    yaml_safe_description = description.replace('"', '\\"') if description else f"{yaml_safe_title}에 대한 AI 요약 뉴스입니다."
    
    # Construct Astro frontmatter
    md_content = f"""---
title: "{yaml_safe_title}"
pubDate: "{datetime.datetime.now().isoformat()}"
description: "{yaml_safe_description}"
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
        # Process up to 15 items, but add a strict delay to prevent Gemini API rate limits (15 RPM free tier)
        # 15 seconds guarantees we only do 4 requests per minute, well below the limit.
        success_count = 0
        target_amount = 15
        
        for item in news_items:
            if success_count >= target_amount:
                break
                
            title, description, content = generate_blog_post(item)
            if title and content:
                save_blog_post(title, description, content)
                success_count += 1
            else:
                safe_title = item['title'].encode('ascii', 'ignore').decode('ascii')
                print(f"Failed to generate post for: {safe_title}")
                
            # Sleep for just 2 seconds since we have fallback
            print("Processing next item...")
            time.sleep(2)
            
        print(f"Bot finished successfully. Generated {success_count} articles.")
    else:
        print("No news found. Exiting.")

if __name__ == "__main__":
    main()
