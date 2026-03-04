import os
import re
import datetime
import string
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
            
            # Filter out promotional text (like TechCrunch events, newsletters)
            promo_spam = ['founder summit', 'disrupt 20', 'ticket', 'save up to', 'register now', 'subscribe to our', 'newsletter']
            
            valid_p = []
            for p in paragraphs:
                text = p.get_text().strip()
                if len(text) > 30:
                    text_lower = text.lower()
                    if not any(spam in text_lower for spam in promo_spam):
                        valid_p.append(text)
                        
            return "\n\n".join(valid_p)
    except Exception as e:
        print(f"  -> Scraping failed: {e}")
    return ""

def fetch_og_image(url):
    """Fetches the Open Graph image (og:image) from an article page."""
    print(f"  -> Trying to fetch OG image from: {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # Try og:image first
            og_img = soup.find('meta', property='og:image')
            if og_img and og_img.get('content'):
                img_url = og_img['content'].strip()
                if img_url.startswith('http'):
                    print(f"  -> Found OG image: {img_url[:80]}...")
                    return img_url
            # Try twitter:image as fallback
            tw_img = soup.find('meta', attrs={'name': 'twitter:image'})
            if tw_img and tw_img.get('content'):
                img_url = tw_img['content'].strip()
                if img_url.startswith('http'):
                    print(f"  -> Found Twitter image: {img_url[:80]}...")
                    return img_url
    except Exception as e:
        print(f"  -> OG image fetch failed: {e}")
    return ""

def get_article_image(news_item):
    """Gets the best available image for an article using a 3-tier strategy:
    1. RSS media image (already extracted)
    2. OG image from original article page
    3. AI-generated image via Pollinations.ai
    """
    # Tier 1: RSS media image
    image_url = news_item.get('image', '')
    if image_url:
        print(f"  -> Using RSS media image")
        return f"![기사 관련 이미지]({image_url})"
    
    # Tier 2: OG image from original article
    og_image = fetch_og_image(news_item.get('link', ''))
    if og_image:
        return f"![기사 관련 이미지]({og_image})"
    
    # Tier 3: AI-generated image via Pollinations.ai
    print(f"  -> Generating AI image via Pollinations.ai")
    title = news_item.get('title', 'AI technology')
    words = [w.strip(string.punctuation) for w in title.split()]
    stop_words = {'the', 'and', 'for', 'with', 'about', 'this', 'that', 'from',
                  'what', 'how', 'has', 'reportedly', 'surpassed', 'annualized',
                  'revenue', 'says', 'could', 'would', 'will', 'just', 'into',
                  'than', 'more', 'after', 'over', 'like', 'been', 'also'}
    keywords = [w.lower() for w in words if len(w) > 2 and w.lower() not in stop_words]
    prompt_text = ' '.join(keywords[:5]) if keywords else 'artificial intelligence technology'
    
    # Build Pollinations.ai URL — free, no API key needed
    encoded_prompt = urllib.parse.quote(f"A professional, modern tech illustration about: {prompt_text}. Clean digital art style, vibrant colors, no text.")
    ai_image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=400&nologo=true"
    
    return f"![AI 생성 이미지]({ai_image_url})"

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
    
    # Scrape the full article text for richer content
    full_article = fetch_article_text(news_item['link'])
    
    text = f"Title: {news_item['title']}\nSource: {news_item['source']}\nSummary: {news_item['summary']}\nLink: {news_item['link']}\nImage URL: {news_item.get('image', '')}"
    if full_article:
        text += f"\n\nFull Article Text:\n{full_article[:6000]}"
    
    # Extract YouTube links before stripping HTML
    yt_links = re.findall(r'(https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https?://youtu\.be/[\w-]+|https?://(?:www\.)?youtube\.com/embed/[\w-]+)', text)
    unique_yt = list(set(yt_links))
    yt_text = "\nYouTube Links: " + ", ".join(unique_yt) if unique_yt else ""
    
    # Strip some HTML tags roughly but use space instead of empty to keep words separated
    text = re.sub('<[^<]+?>', ' ', text) 
    text += yt_text
    
    prompt = f"""
    You are a professional AI news blogger with a friendly, highly readable writing style. 
    Based on the following news article, write a DETAILED, IN-DEPTH, and engaging news blog post in Korean.
    
    CRITICAL INSTRUCTIONS:
    1. Base your article ONLY on the provided news item. COMPLETELY EXCLUDE AND IGNORE any promotional content, advertisements, event ticket sales (e.g., Founder Summit, Disrupt etc.), and newsletter signups. DO NOT include them in your output.
    2. Provide a catchy, click-worthy Korean title on the VERY FIRST line. Do NOT use Markdown heading `#` for the title.
    3. On the SECOND line, write a 1-sentence description. Start this line with 'Description: '.
    4. Tone of Voice: Use polite, engaging, and professional Korean (`~입니다`, `~합니다`, `~있습니다`). Be conversational, explaining the situation as if introducing an exciting new technology.
    
    [LENGTH REQUIREMENT]
    5. The article MUST be at least 800 words in Korean. Write DETAILED explanations, not just summaries. Include background context, industry implications, expert opinions if mentioned, and thorough analysis. DO NOT over-summarize.
    
    [BODY STRUCTURE RULES]
    6. Start the body with an Introduction Section: Introduce the topic with a `<br>` and write AT LEAST 2-3 paragraphs explaining the background and why this news matters.
    
    7. Main Point Section: Use a Header formatted exactly like this: `💡 **[Main Point Title here]**`
       Write a detailed intro paragraph, then break the details down into a bulleted list with AT LEAST 4-5 bullet points.
       - EXACT BULLET FORMAT: `* **[Keyword/Concept]:** [Detailed explanation, at least 2 sentences per bullet]`
       - EVERY single bullet point MUST start with a bolded keyword followed by a colon.
       
    8. Image Placement: Right after this first Main Point Section, you MUST insert the following placeholder verbatim on a new line:
       [IMAGE_PLACEHOLDER]
       
    9. Secondary Section: For the next logical chunk of information, use a Header formatted exactly like this: `🌐 **[Secondary Title here]**`
       Write a detailed intro paragraph for this section, and then follow it with another bulleted list with AT LEAST 3-4 bullet points formatted identically to rule #7.

    10. Additional Analysis Section: Use a Header like this: `📊 **[Analysis/Impact Title here]**`
       Provide deeper analysis of the implications — industry impact, competitor reactions, market trends, or user perspectives. Write at least 2 paragraphs.
       
    11. Conclusion/Future Outlook Section: Use a Header like this: `🚀 **[Future Outlook/Conclusion here]**`
       Provide a thorough concluding analysis of why this matters and what to expect going forward. At least 2 paragraphs.
       
    12. Formatting Rules: 
        - Generous spacing: Always leave an empty line between headers, paragraphs, and lists.
        - Emphasize keywords: Liberally highlight important proper nouns or concepts using bold (`**text**`) inside paragraphs too.
        
    13. YouTube Videos: If any "YouTube Links" are provided in the News Item below, you MUST embed them prominently in the post using this format: `[▶️ 관련 유튜브 영상 보기](YOUTUBE_LINK_HERE)`.
    
    14. At the very end of the post, you MUST include a "출처" (Source) section separated by a horizontal rule (`---`), formatted exactly like this:
       
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
        
        # Replace image placeholder using 3-tier strategy
        image_markdown = get_article_image(news_item)
        
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
        image_markdown = get_article_image(news_item)
        
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
        # Process up to 10 items — retry logic handles Gemini API rate limits
        success_count = 0
        target_amount = 10
        
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
