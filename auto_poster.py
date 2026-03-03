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
            text = "\n\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 30])
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
    You are a professional AI news blogger with a friendly, highly readable writing style. 
    Based on the following news article, write an engaging and informative news blog post in Korean.
    
    CRITICAL INSTRUCTIONS FOR MAXIMUM READABILITY & FORMATTING:
    1. Base your article ONLY on the provided news item.
    2. Provide a catchy, click-worthy Korean title on the VERY FIRST line. Do NOT use Markdown heading `#` for the title.
    3. On the SECOND line, write a 1-sentence description. Start this line with 'Description: '.
    4. Tone of Voice: Use polite, engaging, and professional Korean (`~입니다`, `~합니다`, `~있습니다`). Be conversational, explaining the situation as if introducing an exciting new technology.
    
    [BODY STRUCTURE RULES]
    5. Start the body with an Introduction Section: Introduce the topic with a `<br>` and a paragraph of text.
    
    6. Main Point Section: Use a Header formatted exactly like this: `💡 **[Main Point Title here]**`
       After the header, break the details down into a bulleted list. 
       - EXACT BULLET FORMAT: `* **[Keyword/Concept]:** [Explanation]`
       - EVERY single bullet point MUST start with a bolded keyword followed by a colon. Do not write long paragraphs under bullets. Keep them sharp and readable.
       
    7. Image Placement: Right after this first Main Point Section, you MUST insert the following placeholder verbatim on a new line:
       [IMAGE_PLACEHOLDER]
       
    8. Secondary Section: For the next logical chunk of information, use a Header formatted exactly like this: `🌐 **[Secondary Title here]**`
       Write a brief intro paragraph for this section, and then follow it with another bulleted list formatted identically to rule #6 (`* **[Keyword]:** [Explanation]`).
       
    9. Conclusion/Future Outlook Section: Use a Header like this: `🚀 **[Future Outlook/Conclusion here]**`
       Provide a concluding thought or summary of why this matters.
       
    10. Formatting Rules: 
        - Generous spacing: Always leave an empty line between headers, paragraphs, and lists.
        - Emphasize keywords: Liberally highlight important proper nouns or concepts using bold (`**text**`) inside paragraphs too.
        
    11. YouTube Videos: If any "YouTube Links" are provided in the News Item below, you MUST embed them prominently in the post using this format: `[▶️ 관련 유튜브 영상 보기](YOUTUBE_LINK_HERE)`.
    
    12. At the very end of the post, you MUST include a "출처" (Source) section separated by a horizontal rule (`---`), formatted exactly like this:
       
       ---
       ### 출처
       * **원문 제목:** [English Title]
       * **출처:** [Source Name]
       * [원문 기사 보러가기](the_link_here)
    
    News Item:
    {text}
    """
    
    try:
        response = None
        for attempt in range(5):
            try:
                response = model.generate_content(prompt)
                break
            except Exception as api_e:
                if '429' in str(api_e) or 'exhaust' in str(api_e).lower() or 'quota' in str(api_e).lower():
                    print(f"  -> Gemini API Rate Limit Hit (Attempt {attempt+1}/5). Waiting 30 seconds before retrying...")
                    time.sleep(30)
                else:
                    raise api_e
                    
        if not response:
            raise Exception("Failed after retries")
            
        content = response.text
        
        # Extract title and description, PRESERVING empty lines for markdown
        lines = content.strip().split('\n')
        non_empty_lines = [l.strip() for l in lines if l.strip()]
        
        title = non_empty_lines[0].replace("#", "").strip() if non_empty_lines else "오늘의 AI 뉴스"
        description = f"{title}에 대한 AI 요약 뉴스입니다."
        
        body_start_idx = 1
        # Find where the title ends in the original lines
        for i, line in enumerate(lines):
            if line.strip() == non_empty_lines[0]:
                body_start_idx = i + 1
                break
                
        if len(non_empty_lines) > 1 and non_empty_lines[1].startswith("Description:"):
            description = non_empty_lines[1].replace("Description:", "").strip()
            # Advance start index past description
            for i in range(body_start_idx, len(lines)):
                if lines[i].strip().startswith("Description:"):
                    body_start_idx = i + 1
                    break
            
        body = "\n".join(lines[body_start_idx:])
        
        # Replace image placeholder
        image_url = news_item.get('image', '')
        if image_url:
            image_markdown = f"![기사 관련 이미지]({image_url})"
        else:
            # Extract keywords from title for image generation
            import string
            # Remove punctuation and split
            words = [w.strip(string.punctuation) for w in news_item['title'].split()]
            # Filter out common stop words and short words
            stop_words = {'the', 'and', 'for', 'with', 'about', 'this', 'that', 'from', 'what', 'how', 'has', 'reportedly', 'surpassed', 'annualized', 'revenue'}
            keywords = [w.lower() for w in words if len(w) > 3 and w.lower() not in stop_words]
            
            # Get the top 1-2 keywords
            primary_keywords = "-".join(keywords[:2]) if keywords else "technology-ai"
            safe_keyword = urllib.parse.quote(primary_keywords)
            
            # Use picsum.photos with a seed for distinct, reliable placeholder images (bypasses loremflickr static cat bug)
            image_markdown = f"![AI 관련 이미지](https://picsum.photos/seed/{safe_keyword}/800/400?grayscale=1&blur=2)"
            
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
            # Extract keywords from title for image generation
            import string
            words = [w.strip(string.punctuation) for w in raw_title.split()]
            stop_words = {'the', 'and', 'for', 'with', 'about', 'this', 'that', 'from', 'what', 'how', 'has', 'reportedly', 'surpassed', 'annualized', 'revenue'}
            keywords = [w.lower() for w in words if len(w) > 3 and w.lower() not in stop_words]
            
            primary_keywords = "-".join(keywords[:2]) if keywords else "technology-ai"
            safe_keyword = urllib.parse.quote(primary_keywords)
            
            # Use picsum.photos with a seed for distinct, reliable placeholder images (bypasses loremflickr static cat bug)
            image_markdown = f"![AI 관련 이미지](https://picsum.photos/seed/{safe_keyword}/800/400?grayscale=1&blur=2)"
            
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
💡 **핵심 요약**
* {description}

{image_markdown}

🌐 **기사 내용**
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
        # Process up to 2 items to guarantee successful Gemini generation without quota limits
        success_count = 0
        target_amount = 2
        
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
                
            # Sleep for 5 seconds to pace API requests
            print("Processing next item...")
            time.sleep(5)
            
        print(f"Bot finished successfully. Generated {success_count} articles.")
    else:
        print("No news found. Exiting.")

if __name__ == "__main__":
    main()
