"""Browser detection and WebDriver setup."""

import sys
from pathlib import Path


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
    from selenium import webdriver
    
    browsers = detect_installed_browsers()
    
    if not browsers:
        print("❌ Kein unterstützter Browser gefunden!")
        print("   Bitte installiere Firefox, Chrome oder Edge.")
        sys.exit(1)
    
    for browser in browsers:
        try:
            if browser['name'] == 'Firefox':
                driver = _setup_firefox(browser['path'])
                print(f"🔧 Browser: Firefox (headless)")
                return driver
            elif browser['name'] == 'Chrome':
                driver = _setup_chrome(browser['path'])
                print(f"🔧 Browser: Chrome (headless)")
                return driver
            elif browser['name'] == 'Edge':
                driver = _setup_edge(browser['path'])
                print(f"🔧 Browser: Edge (headless)")
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


def login_to_moodle(driver, username: str, password: str) -> bool:
    """Log in to Moodle using credentials."""
    import time
    
    print(f"\n🔐 Login als {username}...")
    
    driver.get("https://moodle.hs-augsburg.de/login/index.php")
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
        except:
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
    """Navigate to course page and extract all sections with their content."""
    import time
    
    print(f"\n📚 Lade Kursseite...")
    driver.get(course_url)
    time.sleep(2)
    
    course_title = "Unbekannter Kurs"
    try:
        title_elem = driver.find_element("css selector", "h1.h2, .page-header-headings h1")
        course_title = title_elem.text.strip()
        if course_title.startswith("Kurs:"):
            course_title = course_title[5:].strip()
        print(f"   Kurs: {course_title}")
    except:
        print("   Warnung: Kursname nicht gefunden")
    
    sections_data = driver.execute_script("""
        var sections = [];
        var sectionElements = document.querySelectorAll('.section.main.clearfix, li.section.clearfix');
        
        for (var i = 0; i < sectionElements.length; i++) {
            var section = sectionElements[i];
            var sectionName = '';
            
            var nameElem = section.querySelector('.sectionname, h3.sectionname, .section-title');
            if (nameElem) {
                sectionName = nameElem.textContent.trim();
            }
            
            if (!sectionName) {
                sectionName = 'Abschnitt ' + (i + 1);
            }
            
            var resources = [];
            var activityLinks = section.querySelectorAll('a.aalink, a[href*="/mod/"]');
            
            for (var j = 0; j < activityLinks.length; j++) {
                var link = activityLinks[j];
                var href = link.href;
                var text = link.textContent.trim();
                
                var instName = link.querySelector('.instancename');
                if (instName) {
                    text = instName.textContent.trim();
                }
                
                if (!href || !href.includes('/mod/')) continue;
                
                var type = 'unknown';
                var modTypes = ['assign', 'resource', 'folder', 'url', 'page', 
                               'forum', 'book', 'quiz', 'workshop', 'database', 
                               'lesson', 'choice', 'feedback', 'label', 'h5pactivity',
                               'lti', 'scorm', 'glossary', 'wiki', 'data'];
                for (var k = 0; k < modTypes.length; k++) {
                    if (href.includes('/mod/' + modTypes[k] + '/')) {
                        type = modTypes[k];
                        break;
                    }
                }
                
                resources.push({
                    name: text,
                    url: href,
                    type: type
                });
            }
            
            if (resources.length > 0) {
                sections.push({
                    name: sectionName,
                    resources: resources
                });
            }
        }
        
        return sections;
    """)
    
    total_activities = sum(len(s['resources']) for s in sections_data)
    for section in sections_data:
        print(f"   📁 {section['name']}: {len(section['resources'])} Elemente")
    print(f"   Gesamt: {total_activities} Activities in {len(sections_data)} Sektionen")
    
    return sections_data, course_title
