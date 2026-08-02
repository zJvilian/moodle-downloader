"""Browser detection and WebDriver setup."""

import re
import sys
from pathlib import Path


_FALLBACK_SECTION_TITLE = re.compile(r"^(?:abschnitt|section)(?:\s+\d+)?$", re.IGNORECASE)


def _is_fallback_section_title(value: str) -> bool:
    return bool(_FALLBACK_SECTION_TITLE.fullmatch(" ".join(str(value or "").split())))


def detect_installed_browsers() -> list[dict]:
    """Detect which browsers are installed on the system."""
    browsers = []
    
    # Firefox
    firefox_paths = [
        "C:/Program Files/Mozilla Firefox/firefox.exe",
        "C:/Program Files (x86)/Mozilla Firefox/firefox.exe",
        "/usr/bin/firefox",
        "/usr/local/bin/firefox",
        "/Applications/Firefox.app/Contents/MacOS/firefox",
    ]
    for fp in firefox_paths:
        if Path(fp).exists():
            browsers.append({'name': 'Firefox', 'path': fp})
            break
    
    # Chrome
    chrome_paths = [
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/local/bin/google-chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for fp in chrome_paths:
        if Path(fp).exists():
            browsers.append({'name': 'Chrome', 'path': fp})
            break
    
    # Edge
    edge_paths = [
        "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        "/usr/bin/microsoft-edge",
        "/usr/local/bin/microsoft-edge",
    ]
    for fp in edge_paths:
        if Path(fp).exists():
            browsers.append({'name': 'Edge', 'path': fp})
            break
    
    return browsers


def setup_browser_driver():
    """Set up browser WebDriver with automatic fallback."""
    browsers = detect_installed_browsers()
    
    if not browsers:
        print("❌ Kein unterstützter Browser gefunden!")
        print("   Bitte installiere Firefox, Chrome oder Edge.")
        sys.exit(1)
    
    for browser in browsers:
        try:
            if browser['name'] == 'Firefox':
                driver = _setup_firefox(browser['path'])
                print("🔧 Browser: Firefox (headless)")
                return driver
            elif browser['name'] == 'Chrome':
                driver = _setup_chrome(browser['path'])
                print("🔧 Browser: Chrome (headless)")
                return driver
            elif browser['name'] == 'Edge':
                driver = _setup_edge(browser['path'])
                print("🔧 Browser: Edge (headless)")
                return driver
        except Exception as e:
            print(f"   ⚠️ {browser['name']} fehlgeschlagen: {str(e)[:60]}")
            continue
    
    print("❌ Kein Browser konnte gestartet werden!")
    sys.exit(1)


def _setup_firefox(binary_path: str):
    """Set up Firefox with webdriver-manager."""
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    
    try:
        from webdriver_manager.firefox import GeckoDriverManager
        service = Service(GeckoDriverManager().install())
    except Exception:
        service = None
    
    options = Options()
    options.binary_location = binary_path
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.set_preference("dom.webnotifications.enabled", False)
    options.set_preference("dom.push.enabled", False)
    
    if service:
        driver = webdriver.Firefox(service=service, options=options)
    else:
        driver = webdriver.Firefox(options=options)
    
    driver.implicitly_wait(5)
    driver.set_page_load_timeout(15)
    return driver


def _setup_chrome(binary_path: str):
    """Set up Chrome with webdriver-manager."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
    except Exception:
        service = None
    
    options = Options()
    options.binary_location = binary_path
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    if service:
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)
    
    driver.implicitly_wait(5)
    driver.set_page_load_timeout(15)
    return driver


def _setup_edge(binary_path: str):
    """Set up Edge with webdriver-manager."""
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options
    from selenium.webdriver.edge.service import Service
    
    try:
        from webdriver_manager.microsoft import EdgeChromiumDriverManager
        service = Service(EdgeChromiumDriverManager().install())
    except Exception:
        service = None
    
    options = Options()
    options.binary_location = binary_path
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    if service:
        driver = webdriver.Edge(service=service, options=options)
    else:
        driver = webdriver.Edge(options=options)
    
    driver.implicitly_wait(5)
    driver.set_page_load_timeout(15)
    return driver


def login_to_moodle(driver, username: str, password: str, moodle_url: str = "https://moodle.hs-augsburg.de") -> bool:
    """Log in to Moodle using credentials."""
    import time
    from urllib.parse import urlparse
    
    print(f"\n🔐 Login als {username}...")
    
    parsed = urlparse(moodle_url)
    login_url = f"{parsed.scheme}://{parsed.netloc}/login/index.php"
    driver.get(login_url)
    time.sleep(1)
    
    username_field = driver.find_element("id", "username")
    username_field.clear()
    username_field.send_keys(username)
    
    password_field = driver.find_element("id", "password")
    password_field.clear()
    password_field.send_keys(password)
    
    login_button = driver.find_element("id", "loginbtn")
    login_button.click()
    
    time.sleep(2)
    
    if "login" in driver.current_url.lower():
        try:
            error_msg = driver.find_element("css selector", ".alert-danger, .loginerrors")
            print(f"❌ Login fehlgeschlagen: {error_msg.text}")
        except Exception:
            print("❌ Login fehlgeschlagen!")
        return False
    
    print("✅ Login erfolgreich!")
    return True


def get_cookies_from_driver(driver) -> dict:
    """Extract cookies from Selenium driver for use with requests."""
    cookies = {}
    for cookie in driver.get_cookies():
        cookies[cookie['name']] = cookie['value']
    return cookies


def get_course_content(driver, course_url: str) -> tuple[list[dict], str]:
    """Extract the course hierarchy without flattening or duplicating subsections."""
    import time
    
    print("\n📚 Lade Kursseite...")
    driver.get(course_url)
    time.sleep(2)
    
    course_title = "Unbekannter Kurs"
    try:
        title_elem = driver.find_element("css selector", "h1.h2, .page-header-headings h1")
        course_title = title_elem.text.strip()
        if course_title.startswith("Kurs:"):
            course_title = course_title[5:].strip()
        print(f"   Kurs: {course_title}")
    except Exception:
        print("   Warnung: Kursname nicht gefunden")
    
    extraction_script = r"""
        const sectionSelector = '[data-for="section"], li.section, .course-section, .section.main';
        const activitySelector = '[data-for="cmitem"], li.activity, .activity-item';
        const rawSectionElements = Array.from(document.querySelectorAll(sectionSelector));

        function sectionIdentity(section) {
            const idNumber = (section.id || '').match(/^section-(\d+)$/i);
            return section.dataset.sectionid
                || section.dataset.sectionnum
                || section.dataset.number
                || (idNumber ? idNumber[1] : '');
        }

        // Current Moodle themes add nested data-for="section" wrappers. Keep
        // the outer canonical element for each section so its heading and its
        // activities have the same owner. Distinct nested subsections retain
        // their own identity and are therefore preserved.
        const identifiedSections = rawSectionElements.filter(section => sectionIdentity(section));
        const sectionCandidates = identifiedSections.length ? identifiedSections : rawSectionElements;
        const sectionElements = sectionCandidates.filter(section => {
            const identity = sectionIdentity(section);
            if (!identity) return true;
            return !sectionCandidates.some(candidate =>
                candidate !== section
                && candidate.contains(section)
                && sectionIdentity(candidate) === identity
            );
        });
        const sectionElementSet = new Set(sectionElements);
        const sectionNames = new Map();

        function cleanText(element) {
            if (!element) return '';
            const copy = element.cloneNode(true);
            copy.querySelectorAll('.accesshide, .visually-hidden, .sr-only, .section_action_menu, .commands, button')
                .forEach(node => node.remove());
            return copy.textContent.replace(/\s+/g, ' ').trim();
        }

        function sectionName(section, index) {
            if (sectionNames.has(section)) return sectionNames.get(section);
            const labelled = (section.getAttribute('aria-labelledby') || '')
                .split(/\s+/)
                .map(id => document.getElementById(id))
                .filter(Boolean);
            const headings = Array.from(section.querySelectorAll(
                '[data-for="section_title"], [data-for="section_name"], '
                + '.course-section-header .sectionname, .sectionname, .section-title, h3, h2'
            )).filter(item => owningSection(item) === section);
            const candidates = [...labelled, ...headings]
                .map(cleanText)
                .filter(Boolean);
            const meaningful = candidates.find(value =>
                !/^(?:abschnitt|section|thema|topic)(?:\s+\d+)?$/i.test(value)
            );
            const attributeName = section.dataset.sectionname
                || section.dataset.name
                || section.getAttribute('aria-label')
                || '';
            const name = meaningful || attributeName.trim() || candidates[0] || `Abschnitt ${index + 1}`;
            sectionNames.set(section, name);
            return name;
        }

        function sectionId(section, index) {
            return sectionIdentity(section)
                || section.id
                || section.getAttribute('aria-labelledby')
                || `section-${index + 1}-${sectionName(section, index).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
        }

        function owningSection(element) {
            let current = element;
            while (current) {
                if (sectionElementSet.has(current)) return current;
                current = current.parentElement;
            }
            return null;
        }

        function moduleType(href) {
            const match = href.match(/\/mod\/([^/]+)\//i);
            return match ? match[1].toLowerCase() : 'unknown';
        }

        const sections = [];
        sectionElements.forEach((section, index) => {
            const name = sectionName(section, index);
            const path = [];
            const pathIds = [];
            const pathPositions = [];
            let parent = owningSection(section.parentElement);
            const parentChain = [];
            while (parent) {
                parentChain.unshift(parent);
                parent = owningSection(parent.parentElement);
            }
            parentChain.forEach((item) => {
                const itemIndex = sectionElements.indexOf(item);
                path.push(sectionName(item, itemIndex));
                pathIds.push(sectionId(item, itemIndex));
                pathPositions.push(itemIndex + 1);
            });
            path.push(name);
            pathIds.push(sectionId(section, index));
            pathPositions.push(index + 1);

            const resources = [];
            const seen = new Set();
            const activityElements = Array.from(section.querySelectorAll(activitySelector))
                .filter(item => owningSection(item) === section);

            activityElements.forEach((activity, activityIndex) => {
                const moduleLink = activity.querySelector('a.aalink[href*="/mod/"], .activityname a[href*="/mod/"], a[data-action="view-activity"][href*="/mod/"], a[href*="/mod/"]');
                if (moduleLink && moduleLink.href) {
                    const key = moduleLink.href.split('#')[0];
                    if (!seen.has(key)) {
                        seen.add(key);
                        const instance = moduleLink.querySelector('.instancename');
                        resources.push({
                            name: cleanText(instance || moduleLink) || `Aktivität ${activityIndex + 1}`,
                            url: moduleLink.href,
                            type: moduleType(moduleLink.href)
                        });
                    }
                    return;
                }

                const directFiles = Array.from(activity.querySelectorAll('a[href*="pluginfile.php"], a[download]'));
                directFiles.forEach((link, fileIndex) => {
                    const key = link.href.split('#')[0];
                    if (!link.href || seen.has(key)) return;
                    seen.add(key);
                    resources.push({
                        name: cleanText(link) || link.getAttribute('download') || `Datei ${fileIndex + 1}`,
                        filename: link.getAttribute('download') || '',
                        url: link.href,
                        type: 'resource',
                        direct_file: true,
                        same_origin: new URL(link.href).origin === location.origin
                    });
                });

                if (!directFiles.length) {
                    const label = activity.querySelector('.contentwithoutlink, .contentafterlink, .activity-description, .no-overflow');
                    const labelText = cleanText(label);
                    if (label && labelText) {
                        const identifier = activity.id || `label-${index}-${activityIndex}`;
                        if (seen.has(identifier)) return;
                        seen.add(identifier);
                        resources.push({
                            name: labelText.slice(0, 90),
                            url: `${location.href.split('#')[0]}#${identifier}`,
                            type: 'label',
                            html: label.innerHTML
                        });
                    }
                }
            });

            // Older themes sometimes do not wrap activities consistently.
            Array.from(section.querySelectorAll('a[href*="/mod/"]')).forEach(link => {
                if (owningSection(link) !== section) return;
                const key = link.href.split('#')[0];
                if (!link.href || seen.has(key)) return;
                seen.add(key);
                resources.push({name: cleanText(link) || 'Aktivität', url: link.href, type: moduleType(link.href)});
            });

            Array.from(section.querySelectorAll('a[href*="pluginfile.php"], a[download]')).forEach((link, fileIndex) => {
                if (owningSection(link) !== section) return;
                const key = link.href.split('#')[0];
                if (!link.href || seen.has(key)) return;
                seen.add(key);
                resources.push({
                    name: cleanText(link) || link.getAttribute('download') || `Datei ${fileIndex + 1}`,
                    filename: link.getAttribute('download') || '',
                    url: link.href,
                    type: 'resource',
                    direct_file: true,
                    same_origin: new URL(link.href).origin === location.origin
                });
            });

            if (resources.length) {
                sections.push({
                    id: sectionId(section, index),
                    name: name,
                    path: path,
                    path_ids: pathIds,
                    path_positions: pathPositions,
                    level: Math.max(0, path.length - 1),
                    resources: resources
                });
            }
        });
        return sections;
    """

    navigation_script = r"""
        const course = new URL(arguments[0], location.href);
        const accepted = ['section', 'sectionid', 'topic'];
        const links = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/course/view.php"]').forEach(anchor => {
            try {
                const target = new URL(anchor.href, location.href);
                if (target.origin !== course.origin || target.pathname !== course.pathname) return;
                if (target.searchParams.get('id') !== course.searchParams.get('id')) return;
                if (!accepted.some(key => target.searchParams.has(key))) return;
                const clean = new URL(course.href);
                accepted.forEach(key => {
                    if (target.searchParams.has(key)) clean.searchParams.set(key, target.searchParams.get(key));
                });
                clean.hash = '';
                if (!seen.has(clean.href)) {
                    seen.add(clean.href);
                    links.push(clean.href);
                }
            } catch (error) {
                // Ignore malformed links from third-party course formats.
            }
        });
        return links;
    """

    pending = [course_url]
    visited_pages = set()
    merged_sections = {}
    section_order = []
    while pending:
        page_url = pending.pop(0)
        if page_url in visited_pages:
            continue
        if visited_pages:
            driver.get(page_url)
            time.sleep(0.5)
        visited_pages.add(page_url)

        for section in driver.execute_script(extraction_script) or []:
            section_key = str(section.get("id") or section.get("name"))
            if section_key not in merged_sections:
                merged_sections[section_key] = section
                section_order.append(section_key)
                continue
            existing = merged_sections[section_key]
            if len(section.get("path", [])) > len(existing.get("path", [])):
                existing["path"] = section["path"]
                existing["path_ids"] = section.get("path_ids", [])
                existing["path_positions"] = section.get("path_positions", [])
                existing["level"] = section.get("level", 0)
            if _is_fallback_section_title(existing.get("name", "")) and not _is_fallback_section_title(section.get("name", "")):
                existing["name"] = section["name"]
                if existing.get("path"):
                    existing["path"][-1] = section["name"]
            resource_keys = {
                (item.get("type"), item.get("url", "").split("#", 1)[0], item.get("name"))
                for item in existing.get("resources", [])
            }
            for resource in section.get("resources", []):
                key = (resource.get("type"), resource.get("url", "").split("#", 1)[0], resource.get("name"))
                if key not in resource_keys:
                    existing.setdefault("resources", []).append(resource)
                    resource_keys.add(key)

        for linked_page in driver.execute_script(navigation_script, course_url) or []:
            if linked_page not in visited_pages and linked_page not in pending:
                pending.append(linked_page)

    sections_data = [merged_sections[key] for key in section_order]
    
    total_activities = sum(len(s['resources']) for s in sections_data)
    for section in sections_data:
        print(f"   📁 {section['name']}: {len(section['resources'])} Elemente")
    print(f"   Gesamt: {total_activities} Activities in {len(sections_data)} Sektionen")
    
    return sections_data, course_title
