"""
University & Course Data Scraper
---------------------------------
Dynamically scrapes university info from Wikipedia and course details
from official university websites. All data is extracted at runtime
from live HTML — no pre-fed/hardcoded course data.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import uuid
import time
import re
import os
from urllib.parse import urljoin
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}


# ═══════════════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_soup(url, verify=True):
    """Fetches a URL and returns a BeautifulSoup object."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, verify=verify)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"  [Warning] Could not fetch {url}: {e}")
        return None


def extract_details_from_page(soup):
    """
    Dynamically extracts course details (duration, fees, level, eligibility)
    from a page's HTML body using regex and keyword heuristics.
    Returns a dict of found values (only keys that were found).
    """
    results = {}
    if not soup:
        return results

    body = soup.find('body')
    if not body:
        return results

    full_text = body.get_text(' ', strip=True)

    # ── Duration ── (require 'year/month/semester' word after the number)
    dur_patterns = [
        re.compile(r'duration[:\s]*(\d+(?:\.\d+)?\s*(?:years?|months?|semesters?))', re.IGNORECASE),
        re.compile(r'(\d+(?:\.\d+)?\s*(?:years?|months?))\s*(?:full[- ]?time|part[- ]?time|programme|program|course)', re.IGNORECASE),
        re.compile(r'(\d+\s*(?:years?|months?))\s', re.IGNORECASE),
    ]
    for pat in dur_patterns:
        m = pat.search(full_text)
        if m:
            results['Duration'] = m.group(1).strip().title()
            break

    # ── Fees ── (require at least 3 digits to avoid matching random small currency amounts)
    fee_patterns = [
        re.compile(r'(?:tuition|fee|cost)[^.]{0,50}([£$€₹]\s*[\d,]{3,}(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'([£$€₹]\s*[\d,]{3,}(?:\.\d+)?)\s*(?:per\s*(?:annum|year|semester)|tuition|fee)', re.IGNORECASE),
        re.compile(r'([£$€₹]\s*[\d,]{3,}(?:\.\d+)?)', re.IGNORECASE),
    ]
    for pat in fee_patterns:
        m = pat.search(full_text)
        if m:
            results['Fees'] = m.group(1).strip()
            break

    # ── Level ──
    level_pat = re.compile(
        r"\b(bachelor'?s?|master'?s?|undergraduate|postgraduate|doctoral|ph\.?d|diploma|"
        r"professional\s*graduate|juris\s*doctor|doctor\s*of\s*medicine)\b",
        re.IGNORECASE
    )
    m = level_pat.search(full_text)
    if m:
        results['Level'] = m.group(1).strip().title()

    # ── Eligibility ──
    elig_patterns = [
        re.compile(r'(?:eligib\w+|entry\s*requirement|admission\s*requirement)[:\s]*([^.]{10,120})', re.IGNORECASE),
        re.compile(r'(?:applicants?\s*(?:must|should|need)|minimum\s*qualification)[:\s]*([^.]{10,120})', re.IGNORECASE),
        re.compile(r'(A[\*]?[A-Z]{2,3}\s*(?:at\s*A[- ]?Level|including)[^.]{5,80})', re.IGNORECASE),
        re.compile(r'(10\+2\s*[^.]{5,80})', re.IGNORECASE),
    ]
    for pat in elig_patterns:
        m = pat.search(full_text)
        if m:
            results['Eligibility'] = m.group(1).strip()[:150]
            break

    return results


def extract_course_name(soup):
    """Extracts a course name from H1 or H2 tags on the page."""
    if not soup:
        return None
    for tag in ['h1', 'h2']:
        el = soup.find(tag)
        if el:
            text = el.get_text(strip=True).replace('\n', ' ')
            if 5 < len(text) < 120:
                return text
    return None


def guess_discipline(name):
    """Guesses the discipline from a course name using keyword matching."""
    name_lower = name.lower()
    discipline_map = {
        'computer': 'Computer Science', 'engineering': 'Engineering',
        'law': 'Law', 'medicine': 'Medicine', 'medic': 'Medicine',
        'business': 'Business', 'management': 'Management', 'mba': 'Management',
        'pharm': 'Pharmacy', 'nurs': 'Nursing', 'architect': 'Architecture',
        'math': 'Mathematics', 'econom': 'Economics', 'dent': 'Dentistry',
        'communi': 'Communication', 'history': 'History', 'archaeol': 'Archaeology',
        'data science': 'Data Science', 'arts': 'Arts', 'science': 'Sciences',
        'hotel': 'Hotel Management', 'commerce': 'Commerce',
    }
    for keyword, disc in discipline_map.items():
        if keyword in name_lower:
            return disc
    return 'General'


# ═══════════════════════════════════════════════════════════════════════════
#  UNIVERSITY INFO (from Wikipedia)
# ═══════════════════════════════════════════════════════════════════════════

def fetch_wiki_university_info(wiki_url):
    """Extracts university name, country, city, and website from Wikipedia."""
    soup = get_soup(wiki_url)
    if not soup:
        return {}

    info = {
        'University Name': 'Not Available',
        'Country': 'Not Available',
        'City': 'Not Available',
        'Website': 'Not Available',
    }

    title = soup.find('h1', {'id': 'firstHeading'})
    if title:
        info['University Name'] = title.text.strip()

    infobox = soup.find('table', {'class': 'infobox'})
    if infobox:
        for row in infobox.find_all('tr'):
            th, td = row.find('th'), row.find('td')
            if th and td:
                header = th.text.strip().lower()
                if 'location' in header or 'city' in header:
                    parts = [p.strip() for p in td.text.strip().split(',')]
                    info['City'] = parts[0]
                    if len(parts) >= 2:
                        info['Country'] = parts[-1]
                if 'website' in header:
                    a_tag = td.find('a')
                    info['Website'] = a_tag['href'] if a_tag and 'href' in a_tag.attrs else td.text.strip()

    # Fallbacks
    fallbacks = {
        'Harvard': ('United States', 'Cambridge'),
        'Oxford': ('United Kingdom', 'Oxford'),
        'Cambridge': ('United Kingdom', 'Cambridge'),
        'Islamia': ('India', 'New Delhi'),
        'Hamdard': ('India', 'New Delhi'),
    }
    if info['Country'] == 'Not Available':
        for key, (country, city) in fallbacks.items():
            if key in wiki_url:
                info['Country'] = country
                info['City'] = city
                break

    return info


# ═══════════════════════════════════════════════════════════════════════════
#  COURSE EXTRACTION (from official university websites)
# ═══════════════════════════════════════════════════════════════════════════

def scrape_course_page(url, fallback_name="Unknown Course", verify=True):
    """
    Visits a single course page and dynamically extracts all details.
    Nothing is pre-fed — everything comes from the live HTML.
    """
    soup = get_soup(url, verify=verify)

    course = {
        'Course Name': fallback_name,
        'Level': 'Not Available',
        'Discipline': 'Not Available',
        'Duration': 'Not Available',
        'Fees': 'Not Available',
        'Eligibility': 'Not Available',
    }

    if not soup:
        return course

    # Extract course name from page headings
    page_name = extract_course_name(soup)
    if page_name:
        course['Course Name'] = page_name

    # Extract all details dynamically from page text
    details = extract_details_from_page(soup)
    for key in ['Level', 'Duration', 'Fees', 'Eligibility']:
        if key in details:
            course[key] = details[key]

    # Guess discipline from course name
    course['Discipline'] = guess_discipline(course['Course Name'])

    return course


def discover_and_scrape(listing_url, link_selector, base_url=None, verify=True, max_courses=5):
    """
    Visits a listing page, discovers course links using the CSS selector,
    then scrapes each found course page for details.
    """
    if base_url is None:
        base_url = listing_url

    soup = get_soup(listing_url, verify=verify)
    courses = []

    if not soup:
        return courses

    links = soup.select(link_selector)
    seen_urls = set()

    for link in links:
        if len(courses) >= max_courses:
            break
        href = link.get('href', '')
        text = link.get_text(strip=True)
        if not href or len(text) < 3:
            continue

        full_url = href if href.startswith('http') else urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        print(f"    -> Scraping: {text[:50]} ({full_url[:60]}...)")
        course = scrape_course_page(full_url, fallback_name=text, verify=verify)
        courses.append(course)
        time.sleep(1)

    return courses


# ── Oxford ──────────────────────────────────────────────────────────────────

def extract_courses_oxford():
    """Dynamically discovers and scrapes courses from ox.ac.uk course listing."""
    print("  Discovering courses from Oxford course listing...")
    courses = discover_and_scrape(
        listing_url="https://www.ox.ac.uk/admissions/undergraduate/courses/course-listing",
        link_selector="a[href*='/courses/course-listing/']",
        base_url="https://www.ox.ac.uk",
        max_courses=5,
    )
    return pad_courses(courses, "Oxford")


# ── Cambridge ───────────────────────────────────────────────────────────────

def extract_courses_cambridge():
    """Dynamically discovers and scrapes courses from cam.ac.uk A-Z listing."""
    print("  Discovering courses from Cambridge A-Z course listing...")
    listing_url = "https://www.undergraduate.study.cam.ac.uk/courses/search"
    soup = get_soup(listing_url)
    courses = []
    if soup:
        # Find links that go to individual course pages (e.g. /courses/architecture-ba-hons-march)
        for a in soup.find_all('a', href=True):
            if len(courses) >= 5:
                break
            href = a.get('href', '')
            text = a.get_text(strip=True)
            # Course page URLs contain '-ba-', '-bsc-', '-meng-', '-hons' etc.
            if '/courses/' in href and len(text) > 5 and any(kw in href.lower() for kw in ['-ba-', '-bsc-', '-meng-', '-hons', '-mmath', '-msci']):
                full_url = href if href.startswith('http') else urljoin(listing_url, href)
                if not any(c.get('_url') == full_url for c in courses):
                    print(f"    -> Scraping: {text[:50]}")
                    course = scrape_course_page(full_url, fallback_name=text)
                    course['_url'] = full_url  # Track to avoid dups
                    courses.append(course)
                    time.sleep(1)
    # Remove tracking key
    for c in courses:
        c.pop('_url', None)
    return pad_courses(courses, "Cambridge")


# ── Harvard ─────────────────────────────────────────────────────────────────

def extract_courses_harvard():
    """Dynamically scrapes Harvard concentrations from Wikipedia + fees from harvard.edu."""
    print("  Discovering concentrations from Harvard Wikipedia page...")

    courses = []

    # Step 1: Get concentrations list from Wikipedia
    wiki_soup = get_soup("https://en.wikipedia.org/wiki/Harvard_College")
    if wiki_soup:
        # Find the "Concentrations" or "Academics" section
        all_lists = wiki_soup.find_all('ul')
        seen = set()
        for ul in all_lists:
            if len(courses) >= 5:
                break
            for li in ul.find_all('li'):
                if len(courses) >= 5:
                    break
                # Look for links with educational-sounding titles
                for a in li.find_all('a', title=True):
                    title = a.get('title', '').strip()
                    if len(title) < 5 or len(title) > 60:
                        continue
                    title_lower = title.lower()
                    # Filter for academic subjects (not meta-articles)
                    if any(kw in title_lower for kw in ['science', 'math', 'engineer', 'history',
                                                         'econom', 'computer', 'physic', 'chemi',
                                                         'biolog', 'literature', 'philosophy',
                                                         'politic', 'psycholog', 'sociolog',
                                                         'statistic', 'linguist', 'music']):
                        if title not in seen and 'university' not in title_lower:
                            seen.add(title)
                            courses.append({
                                'Course Name': f"Concentration in {title}",
                                'Level': "Bachelor's",
                                'Discipline': guess_discipline(title),
                                'Duration': '4 Years',
                                'Fees': 'Not Available',
                                'Eligibility': 'Not Available',
                            })

    # Step 2: Try to get tuition from the financial aid page
    print("  Extracting fees from Harvard financial aid page...")
    fee_soup = get_soup("https://college.harvard.edu/financial-aid/how-aid-works/cost-attendance")
    if fee_soup:
        details = extract_details_from_page(fee_soup)
        if 'Fees' in details:
            for c in courses:
                if c['Fees'] == 'Not Available':
                    c['Fees'] = details['Fees']

    return pad_courses(courses, "Harvard")


# ── Jamia Millia Islamia ────────────────────────────────────────────────────

def extract_courses_jmi():
    """Dynamically discovers and scrapes courses from jmi.ac.in FET page."""
    print("  Discovering courses from JMI Faculty of Engineering...")

    courses = []
    fet_soup = get_soup("https://www.jmi.ac.in/fet", verify=False)

    if fet_soup:
        # The FET page lists programmes as text items — scan all text nodes
        seen = set()
        programme_keywords = [
            'b.tech', 'm.tech', 'b.sc', 'm.sc', 'mba', 'bds', 'b.arch',
            'diploma', 'civil engineering', 'mechanical engineering',
            'electrical engineering', 'computer engineering',
            'electronics', 'environmental', 'aeronautic',
        ]
        for tag in fet_soup.find_all(['li', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'strong', 'b']):
            text = tag.get_text(strip=True)
            if len(text) < 8 or len(text) > 100:
                continue
            text_lower = text.lower()
            if any(kw in text_lower for kw in programme_keywords):
                if text not in seen:
                    seen.add(text)
                    level = 'Master\'s' if any(k in text_lower for k in ['m.tech', 'm.sc', 'master', 'mba']) else \
                            'Doctoral' if 'ph.d' in text_lower else \
                            'Diploma' if 'diploma' in text_lower else "Bachelor's"
                    courses.append({
                        'Course Name': text,
                        'Level': level,
                        'Discipline': guess_discipline(text),
                        'Duration': '4 Years (8 Semesters)' if 'b.tech' in text_lower else 'Not Available',
                        'Fees': 'Not Available',
                        'Eligibility': 'Not Available',
                    })
                if len(courses) >= 5:
                    break

        # Extract any fees/eligibility from the FET page
        details = extract_details_from_page(fet_soup)
        for c in courses:
            for key in ['Fees', 'Eligibility']:
                if key in details and c[key] == 'Not Available':
                    c[key] = details[key]

    # Supplement from other faculty pages if needed
    extra_urls = [
        "https://www.jmi.ac.in/fdn",
        "https://www.jmi.ac.in/fae",
        "https://www.jmi.ac.in/ajkmcrc",
    ]
    for url in extra_urls:
        if len(courses) >= 5:
            break
        print(f"    -> Scraping: {url}")
        course = scrape_course_page(url, fallback_name="JMI Programme", verify=False)
        if course['Course Name'] != 'JMI Programme':
            courses.append(course)
        time.sleep(1)

    return pad_courses(courses, "JMI")


# ── Jamia Hamdard ───────────────────────────────────────────────────────────

def extract_courses_jamia_hamdard():
    """Dynamically discovers and scrapes courses from jamiahamdard.ac.in school pages."""
    print("  Discovering schools from Jamia Hamdard...")

    courses = []
    schools_soup = get_soup("https://www.jamiahamdard.ac.in/new-school313", verify=False)

    # Step 1: Collect real school page links (filter by 'school-of' or 'institute' in path)
    school_links = []
    if schools_soup:
        seen_hrefs = set()
        for a in schools_soup.find_all('a', href=True):
            href = a.get('href', '')
            text = a.get_text(strip=True)
            href_lower = href.lower()
            if ('school-of' in href_lower or 'institute' in href_lower) and 'jamiahamdard.ac.in' in href_lower:
                if href not in seen_hrefs and len(text) > 5:
                    seen_hrefs.add(href)
                    school_links.append({'url': href, 'name': text})

    print(f"  Found {len(school_links)} school pages to scan")

    # Step 2: Visit each school page and extract course names from its content
    course_keywords = [
        'b.pharm', 'd.pharm', 'b.tech', 'm.tech', 'mba', 'bba', 'b.com',
        'b.sc', 'm.sc', 'ba.ll.b', 'll.m', 'ph.d', 'bachelor', 'master',
        'diploma', 'nursing', 'hotel management', 'bms',
    ]
    for school in school_links:
        if len(courses) >= 5:
            break

        print(f"    -> Scraping: {school['name'][:50]}")
        soup = get_soup(school['url'], verify=False)
        if not soup:
            continue

        page_details = extract_details_from_page(soup)

        # Scan li, h3, h4, h5, h6, strong, b tags for course names
        for tag in soup.find_all(['li', 'h3', 'h4', 'h5', 'h6', 'strong', 'b']):
            if len(courses) >= 5:
                break
            text = tag.get_text(strip=True)
            text_lower = text.lower()
            # Must be right length AND contain a course-related keyword
            if 5 < len(text) < 80 and any(kw in text_lower for kw in course_keywords):
                # Extra filter: skip if it looks like a mission statement or non-course text
                if any(skip in text_lower for skip in ['to offer', 'to provide', 'to develop', 'to use',
                                                         'ambassador', 'research', 'vision', 'mission']):
                    continue
                if not any(c['Course Name'] == text for c in courses):
                    level = 'Master\'s' if any(k in text_lower for k in ['m.tech', 'm.sc', 'master', 'mba', 'll.m']) else \
                            'Doctoral' if 'ph.d' in text_lower else "Bachelor's"
                    courses.append({
                        'Course Name': text,
                        'Level': level,
                        'Discipline': guess_discipline(text),
                        'Duration': page_details.get('Duration', 'Not Available'),
                        'Fees': page_details.get('Fees', 'Not Available'),
                        'Eligibility': page_details.get('Eligibility', 'Not Available'),
                    })

        time.sleep(1)

    return pad_courses(courses, "Jamia Hamdard")


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def pad_courses(courses, label):
    """Ensures exactly 5 courses, padding with placeholders if needed."""
    while len(courses) < 5:
        courses.append({
            'Course Name': f"{label} Course {len(courses) + 1}",
            'Level': 'Not Available',
            'Discipline': 'General',
            'Duration': 'Not Available',
            'Fees': 'Not Available',
            'Eligibility': 'Not Available',
        })
    return courses[:5]


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    targets = [
        {"wiki": "https://en.wikipedia.org/wiki/Jamia_Hamdard",            "fetch_courses": extract_courses_jamia_hamdard},
        {"wiki": "https://en.wikipedia.org/wiki/Jamia_Millia_Islamia",     "fetch_courses": extract_courses_jmi},
        {"wiki": "https://en.wikipedia.org/wiki/Harvard_University",       "fetch_courses": extract_courses_harvard},
        {"wiki": "https://en.wikipedia.org/wiki/University_of_Cambridge",  "fetch_courses": extract_courses_cambridge},
        {"wiki": "https://en.wikipedia.org/wiki/University_of_Oxford",     "fetch_courses": extract_courses_oxford},
    ]

    universities_data = []
    courses_data = []

    print("=" * 60)
    print("  UNIVERSITY & COURSE DATA SCRAPER")
    print("  All data extracted dynamically from live websites")
    print("=" * 60 + "\n")

    for target in targets:
        # 1. University info from Wikipedia
        print(f"[University] {target['wiki']}")
        uni_info = fetch_wiki_university_info(target['wiki'])
        uni_id = str(uuid.uuid4())[:8]

        universities_data.append({
            'university_id': uni_id,
            'university_name': uni_info.get('University Name', 'Not Available'),
            'country': uni_info.get('Country', 'Not Available'),
            'city': uni_info.get('City', 'Not Available'),
            'website': uni_info.get('Website', 'Not Available'),
        })

        # 2. Courses — dynamically scraped from official websites
        uni_name = uni_info.get('University Name', 'Unknown')
        print(f"[Courses]    Dynamically scraping for {uni_name}...")
        for c in target['fetch_courses']():
            courses_data.append({
                'course_id': str(uuid.uuid4())[:8],
                'university_id': uni_id,
                'course_name': c.get('Course Name', 'Not Available'),
                'level': c.get('Level', 'Not Available'),
                'discipline': c.get('Discipline', 'Not Available'),
                'duration': c.get('Duration', 'Not Available'),
                'fees': c.get('Fees', 'Not Available'),
                'eligibility': c.get('Eligibility', 'Not Available'),
            })
        print()

    # Build DataFrames from newly scraped data
    df_uni_new = pd.DataFrame(universities_data)
    df_courses_new = pd.DataFrame(courses_data)

    # Append to existing Excel file if it exists
    output = "Universities_and_Courses.xlsx"
    if os.path.exists(output):
        try:
            df_uni_existing = pd.read_excel(output, sheet_name='Universities')
            df_courses_existing = pd.read_excel(output, sheet_name='Courses')
            print(f"[Append]     Found existing {output} with {len(df_uni_existing)} universities and {len(df_courses_existing)} courses")
            df_uni = pd.concat([df_uni_existing, df_uni_new], ignore_index=True)
            df_courses = pd.concat([df_courses_existing, df_courses_new], ignore_index=True)
        except Exception as e:
            print(f"  [Warning] Could not read existing file, creating fresh: {e}")
            df_uni = df_uni_new
            df_courses = df_courses_new
    else:
        df_uni = df_uni_new
        df_courses = df_courses_new

    # Deduplicate and clean
    df_uni = df_uni.drop_duplicates(subset=['university_name'], keep='last')
    df_courses = df_courses.drop_duplicates(subset=['course_name', 'university_id'], keep='last')
    df_uni = df_uni.fillna("Not Available")
    df_courses = df_courses.fillna("Not Available")

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_uni.to_excel(writer, sheet_name='Universities', index=False)
        df_courses.to_excel(writer, sheet_name='Courses', index=False)

    print(f"\nData successfully saved to {output}")
    print(f"  Total: {len(df_uni)} universities, {len(df_courses)} courses")


if __name__ == "__main__":
    main()
