import time
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, StaleElementReferenceException
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class WebsiteTracker:
    def __init__(self, pin_code="500084", max_retries=3, email_config=None):
        self.pin_code = pin_code
        self.max_retries = max_retries
        self.email_config = email_config
        self.chrome_options = Options()
        self.chrome_options.add_argument('--headless')  # Run in headless mode
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.chrome_options.add_argument('--disable-gpu')
        self.chrome_options.add_argument('--window-size=1920,1080')
        self.last_notification = {}  # Track last notification time for each URL

    def create_driver(self):
        """Create a new browser session"""
        return webdriver.Chrome(options=self.chrome_options)

    def wait_and_find_element(self, driver, by, value, timeout=15):
        """Helper method to wait for and find an element with retry logic"""
        for attempt in range(self.max_retries):
            try:
                element = WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
                return element
            except TimeoutException:
                if attempt == self.max_retries - 1:
                    raise
                print(f"Attempt {attempt + 1} failed, retrying...")
                time.sleep(3)

    def enter_pin_code(self, driver):
        try:
            # Wait for the PIN code input field with retry logic
            pin_input = self.wait_and_find_element(driver, By.ID, "search")
            
            # Clear any existing value and enter the PIN code
            pin_input.clear()
            time.sleep(3)  # Small delay after clear
            pin_input.send_keys(self.pin_code)
            time.sleep(3)  # Small delay after entering PIN
            
            # Trigger input event to make dropdown appear
            driver.execute_script("""
                let event = new Event('input', {
                    bubbles: true,
                    cancelable: true,
                });
                arguments[0].dispatchEvent(event);
            """, pin_input)
            
            # Wait for the dropdown and click the first location
            time.sleep(3)  # Increased wait time for dropdown
            
            # Try to find and click the location with retry logic
            for attempt in range(self.max_retries):
                try:
                    location = self.wait_and_find_element(driver, By.CLASS_NAME, "searchitem-name")
                    # Scroll the element into view
                    driver.execute_script("arguments[0].scrollIntoView(true);", location)
                    time.sleep(3)  # Wait for scroll to complete
                    location.click()
                    break
                except (ElementClickInterceptedException, StaleElementReferenceException):
                    if attempt == self.max_retries - 1:
                        raise
                    print(f"Click attempt {attempt + 1} failed, retrying...")
                    time.sleep(2)
            
            # Wait for the page to update after location selection
            time.sleep(3)  # Increased wait time after location selection
            return True
            
        except Exception as e:
            print(f"Error entering PIN code: {str(e)}")
            return False

    def check_add_to_cart_status(self, url):
        driver = self.create_driver()
        try:
            driver.get(url)
            time.sleep(3)  # Wait for initial page load
            
            # First enter the PIN code and select location
            if not self.enter_pin_code(driver):
                return {
                    'found': False,
                    'is_disabled': None,
                    'status': 'Failed to enter PIN code'
                }
            
            # Get the attribute value directly from the HTML
            disabled_attr = driver.execute_script("""
                const element = document.getElementsByClassName('add-to-cart')[0];
                return element.getAttribute('disabled');
            """)
            
            # Check if the button is disabled using the actual attribute value
            is_disabled = disabled_attr == "true"
            
            return {
                'found': True,
                'is_disabled': is_disabled,
                'status': 'Out of Stock' if is_disabled else 'In Stock'
            }
                
        except Exception as e:
            print(f"Error checking {url}: {str(e)}")
            return {
                'found': False,
                'is_disabled': None,
                'status': f'Error: {str(e)}'
            }
        finally:
            driver.quit()

    def send_email_notification(self, product_url, status):
        """Send email notification when a product is in stock"""
        if not self.email_config:
            return

        # Check if we've sent a notification in the last hour for this URL
        current_time = datetime.now()
        if product_url in self.last_notification:
            time_diff = (current_time - self.last_notification[product_url]).total_seconds()
            if time_diff < 3600:  # 1 hour in seconds
                return

        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['sender_email']
            msg['To'] = self.email_config['receiver_email']
            msg['Subject'] = f"Product In Stock Alert: {product_url}"

            body = f"""
            Hello,

            The following product is now in stock:

            Product URL: {product_url}
            Status: {status}
            Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}

            Please check the website to place your order.

            Best regards,
            Lassi Tracker
            """

            msg.attach(MIMEText(body, 'plain'))

            # Create SMTP session
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'])
            server.starttls()
            server.login(self.email_config['sender_email'], self.email_config['password'])
            server.send_message(msg)
            server.quit()

            # Update last notification time
            self.last_notification[product_url] = current_time
            print(f"Email notification sent for {product_url}")

        except Exception as e:
            print(f"Error sending email notification: {str(e)}")

    def monitor_websites(self, urls):
        print(f"\nChecking websites at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        for url in urls:
            print(f"\nChecking: {url}")
            for attempt in range(self.max_retries):
                try:
                    result = self.check_add_to_cart_status(url)
                    if result:
                        print(f"Results for {url}:")
                        print(f"Button Found: {'Yes' if result['found'] else 'No'}")
                        if result['found']:
                            print(f"Button Disabled: {'Yes' if result['is_disabled'] else 'No'}")
                            print(f"Status: {result['status']}")
                            
                            # Send email notification if product is in stock
                            if not result['is_disabled']:
                                self.send_email_notification(url, result['status'])
                    break
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        print(f"Failed after {self.max_retries} attempts: {str(e)}")
                    else:
                        print(f"Attempt {attempt + 1} failed, retrying...")
                        time.sleep(3)

# Example usage
if __name__ == "__main__":
    # Define the websites to monitor
    websites = [
        # "https://shop.amul.com/en/product/amul-high-protein-rose-lassi-200-ml-or-pack-of-30",
        "https://shop.amul.com/en/product/amul-high-protein-blueberry-shake-200-ml-or-pack-of-30",
        # "https://shop.amul.com/en/product/amul-high-protein-buttermilk-200-ml-or-pack-of-30",
        # "https://shop.amul.com/en/product/amul-high-protein-plain-lassi-200-ml-or-pack-of-30"
    ]
    
    # Email configuration
    email_config = {
        'sender_email': os.getenv('SENDER_EMAIL'),
        'receiver_email': os.getenv('RECEIVER_EMAIL'),
        'password': os.getenv('EMAIL_PASSWORD'),
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587
    }
    
    # Create and start the tracker
    tracker = WebsiteTracker(pin_code="500084", email_config=email_config)
    print("Starting website monitoring...")
    tracker.monitor_websites(websites) 