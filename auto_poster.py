import os
import re
import datetime
import string
import random
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
    alt_text = news_item.get('title', 'AI 트렌드 뉴스 이미지').replace('"', "'")
    
    # Tier 1: RSS media image
    image_url = news_item.get('image', '')
    if image_url:
        print(f"  -> Using RSS media image")
        return f"![{alt_text}]({image_url})"
    
    # Tier 2: OG image from original article
    og_image = fetch_og_image(news_item.get('link', ''))
    if og_image:
        return f"![{alt_text}]({og_image})"
    
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
    
    return f"![{alt_text}]({ai_image_url})"

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
    
    # Diverse AI / Tech news RSS feeds
    rss_urls = [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/rss/artificial-intelligence/index.xml",      # The Verge AI
        "https://venturebeat.com/category/ai/feed/",                           # VentureBeat AI
        "https://www.wired.com/feed/category/artificial-intelligence/latest/rss",  # Wired AI
        "https://www.technologyreview.com/feed/",                              # MIT Technology Review
        "https://arstechnica.com/tag/artificial-intelligence/feed/",           # Ars Technica AI
        "https://www.artificialintelligence-news.com/feed/",                   # AI News
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
    
    # Randomize article structure to avoid template-like AI feel
    structures = ["분석형", "이야기형", "비교형", "현장형"]
    style = random.choice(structures)
    
    intro_styles = [
        "충격적인 통계나 팩트로 시작하세요.",
        "독자에게 질문을 던지며 시작하세요.",
        "관련된 최근 사건이나 트렌드를 언급하며 시작하세요.",
        "핵심 인물의 발언을 인용하며 시작하세요.",
        "이 뉴스가 일반 사용자에게 미치는 영향으로 시작하세요.",
    ]
    intro_guide = random.choice(intro_styles)
    
    prompt = f"""
    당신은 AI/기술 분야를 깊이 이해하고 있는 전문 블로거입니다.
    아래 뉴스 기사를 바탕으로 한국어로 블로그 글을 작성하세요.
    
    [핵심 원칙]
    1. 제공된 뉴스만 기반으로 작성하세요. 광고, 이벤트 홍보, 뉴스레터 관련 내용은 완전히 제외하세요.
    2. 첫 줄에 클릭을 유도하는 한국어 제목을 쓰세요. 마크다운 헤딩(#) 사용 금지.
    3. 두 번째 줄에 'Description: '로 시작하는 1문장 요약을 쓰세요.
    
    [글쓰기 스타일 — 이것이 가장 중요합니다]
    - 이번 글의 스타일: **{style}**
    - 도입부: {intro_guide}
    - "안녕하세요" 같은 인사말로 시작하지 마세요.
    - ~입니다/~합니다 체를 기본으로 하되, 때때로 의문문("~일까요?"), 감탄문("~놀랍습니다"), 
      구어체("솔직히 말해서", "사실 이건")를 자연스럽게 섞으세요.
    - 매 문단마다 볼드체를 남발하지 마세요. 정말 핵심 키워드만 강조하세요.
    - 이모지를 소제목에 매번 넣지 마세요. 필요한 곳에만 자연스럽게 사용하세요.
    
    [글 구조]
    - 자유로운 구조로 작성하세요. 매번 같은 패턴을 반복하지 마세요.
    - 소제목은 2-3개 정도 사용하되 ## 마크다운 형식으로 쓰세요.
    - 불릿 리스트와 일반 문단을 적절히 섞으세요. 불릿만 나열하지 마세요.
    - 문단 사이에 빈 줄을 넣어 가독성을 확보하세요.
    
    [필수 포함 요소]
    - 최소 800단어 이상으로 상세하게 작성하세요.
    - 배경 맥락을 충분히 설명하세요 (이 뉴스가 왜 중요한지).
    - **필자의 분석이나 관점**을 반드시 1-2곳에 포함하세요. 
      예: "이 부분에서 주목할 점은...", "개인적으로는 ~라고 생각한다", 
      "업계 흐름을 보면 ~할 가능성이 높다"
    - 이미지 위치: 본문 중간쯤에 다음 플레이스홀더를 삽입하세요:
      [IMAGE_PLACEHOLDER]
    
    [유튜브]
    - 뉴스 아이템에 YouTube 링크가 있으면 `[▶️ 관련 영상 보기](URL)` 형태로 삽입하세요.
    
    [출처 — 반드시 글 마지막에 포함]
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

def get_existing_posts():
    """Reads existing blog posts and returns sets of titles and URLs for dedup."""
    blog_dir = os.path.join(os.path.dirname(__file__), "src", "content", "blog")
    existing_titles = set()
    existing_urls = set()
    if not os.path.isdir(blog_dir):
        return existing_titles, existing_urls
    for fname in os.listdir(blog_dir):
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(blog_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()  # Read ENTIRE file (bug fix: was 2000 bytes)
            # Extract original English title from 출처 section
            m = re.search(r'원문 제목[：:]\*?\*?\s*(.+)', content)
            if m:
                existing_titles.add(m.group(1).strip())
            # Extract source URL for double-check
            u = re.search(r'원문 기사 보러가기\]\((https?://[^\)]+)\)', content)
            if u:
                existing_urls.add(u.group(1).strip())
        except:
            pass
    return existing_titles, existing_urls

def main():
    print("Starting AI News Bot...")
    news_items = fetch_rss_news()
    
    if news_items:
        # Generate and save a separate post for each of the top items
        # Load existing titles AND URLs for robust dedup
        existing_titles, existing_urls = get_existing_posts()
        print(f"Found {len(existing_titles)} existing titles, {len(existing_urls)} existing URLs for dedup check.")
        
        success_count = 0
        target_amount = 10
        
        for item in news_items:
            if success_count >= target_amount:
                break
            
            # Skip if this article was already posted (title OR URL match)
            item_title = item['title'].strip()
            item_url = item.get('link', '').strip()
            
            if item_title in existing_titles:
                safe_title = item_title.encode('ascii', 'ignore').decode('ascii')
                print(f"Skipping duplicate (title match): {safe_title}")
                continue
            
            if item_url and item_url in existing_urls:
                safe_title = item_title.encode('ascii', 'ignore').decode('ascii')
                print(f"Skipping duplicate (URL match): {safe_title}")
                continue
                
            title, description, content = generate_blog_post(item)
            if title and content:
                save_blog_post(title, description, content)
                # Add to dedup sets so same-run doesn't duplicate
                existing_titles.add(item_title)
                if item_url:
                    existing_urls.add(item_url)
                success_count += 1
            else:
                safe_title = item_title.encode('ascii', 'ignore').decode('ascii')
                print(f"Failed to generate post for: {safe_title}")
                
            # Sleep for 5 seconds to pace API requests
            print("Processing next item...")
            time.sleep(5)
            
        print(f"Bot finished successfully. Generated {success_count} articles.")
    else:
        print("No news found. Exiting.")

if __name__ == "__main__":
    main()
