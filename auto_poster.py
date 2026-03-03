import os
import re
import datetime
from dotenv import load_dotenv
import feedparser
import urllib.parse
import time
import requests
import google.generativeai as genai
from deep_translator import GoogleTranslator
from bs4 import BeautifulSoup

def fetch_article_text(url):
    """Fetches the actual article content from the URL to bypass short RSS summaries."""
    print(f"  -> Scraping full text from: {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # Extract paragraphs
            paragraphs = soup.find_all('p')
            text = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 30])
            return text
    except Exception as e:
        print(f"  -> Scraping failed: {e}")
    return ""

# Initialize translator
translator = GoogleTranslator(source='auto', target='ko')

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
            import string
            words = [w.strip(string.punctuation) for w in news_item['title'].split() if len(w) > 3]
            keyword = words[0] if words else "technology"
            safe_keyword = urllib.parse.quote(keyword)
            # Use picsum.photos with a seed for consistent, reliable placeholder images
            image_markdown = f"![AI 관련 이미지](https://picsum.photos/seed/{safe_keyword}/800/400)"
            
        body = body.replace("[IMAGE_PLACEHOLDER]", image_markdown)
        
        return title, description, body
    except Exception as e:
        print(f"Error generating content (falling back to RSS data): {e}")
        # Fallback to pure RSS data when Gemini API hits a rate limit
        # Remove [속보] and translate title
        raw_title = news_item['title']
        try:
            title = translator.translate(raw_title)
        except:
            title = raw_title
            
        # Strip HTML from description to avoid frontend layout breaks (<p><a href...>)
        raw_desc_html = news_item.get('summary', '')
        try:
            soup = BeautifulSoup(raw_desc_html, "html.parser")
            raw_desc_clean = soup.get_text(separator=' ').strip()
        except:
            raw_desc_clean = re.sub('<[^<]+?>', ' ', raw_desc_html).strip()
            
        raw_desc = raw_desc_clean[:100] + "..." if raw_desc_clean else f"{raw_title} news summary."
        
        try:
            description = translator.translate(raw_desc)
        except:
            description = raw_desc
        
        # Build a basic fallback body
        image_url = news_item.get('image', '')
        if image_url:
            image_markdown = f"![기사 관련 이미지]({image_url})"
        else:
            import string
            # Use original English title to extract keyword for Picsum seed
            words = [w.strip(string.punctuation) for w in raw_title.split() if w.lower() not in ['the', 'and', 'for', 'with', 'about'] and len(w) > 3]
            keyword = words[0].lower() if words else "technology"
            safe_keyword = urllib.parse.quote(keyword)
            # Use picsum.photos with a seed for consistent, reliable placeholder images
            image_markdown = f"![AI 관련 이미지](https://picsum.photos/seed/{safe_keyword}/800/400)"
            
        # If RSS summary is too short (like TechCrunch), try to fetch the real article text
        article_text = fetch_article_text(news_item['link'])
        if len(article_text) > 200:
            raw_summary_html = article_text
        else:
            raw_summary_html = news_item.get('summary', '조금 더 상세한 정보를 원하시면 원문을 확인해주세요.')
            
        try:
            soup2 = BeautifulSoup(raw_summary_html, "html.parser")
            raw_summary_clean = soup2.get_text(separator='\n\n').strip()
        except:
            raw_summary_clean = re.sub('<[^<]+?>', ' ', raw_summary_html).strip()
        
        # Limit the text length to ensure it translates correctly
        raw_summary_clean = raw_summary_clean[:4000]
        
        # Split summary into smaller chunks if it's too long, as deep_translator has a 5000 char limit
        # For RSS fallback, usually the summary isn't that long, but just to be safe
        try:
            translated_summary = translator.translate(raw_summary_clean)
        except:
            translated_summary = raw_summary_clean
            
        body = f"""
## 📌 핵심 요약
* {description}

{image_markdown}

## 🚀 기사 내용
{translated_summary}

---
### 🔗 원문 정보
* **원문 제목:** {raw_title}
* **출처:** {news_item['source']}
* [원문 기사 보러가기]({news_item['link']})
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
