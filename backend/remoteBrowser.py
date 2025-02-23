from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, VideoStreamTrack
import asyncio
import fractions
import time
import base64
import av
import numpy as np
import io

class BrowserVideoStreamTrack(VideoStreamTrack):
    def __init__(self, driver):
        super().__init__()
        self._driver = driver
        self._timestamp = 0
        self._last_frame_time = time.time()
        
    async def recv(self):
        await asyncio.sleep(1/30)  # 30fps
        try:
            # Capture screenshot using CDP
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self._driver.execute_cdp_cmd,
                'Page.captureScreenshot',
                {'format': 'png'}
            )
            
            # Decode base64 image
            image_data = base64.b64decode(result['data'])
            
            # Create frame from PNG data
            container = av.open(io.BytesIO(image_data), format='png')
            frame = next(container.decode(video=0))
            
            # Set frame timing
            pts, time_base = await self._next_timestamp()
            frame.pts = pts
            frame.time_base = time_base
            
            return frame
            
        except Exception as e:
            print(f"Error capturing frame: {e}")
            raise

    async def _next_timestamp(self):
        self._timestamp += 1
        return self._timestamp, fractions.Fraction(1, 30)

class RemoteBrowser:
    def __init__(self):
        self.driver = None
        self.pc = None

    async def initialize(self):
        chrome_options = Options()
        chrome_options.add_argument("--window-size=1024,768")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--remote-debugging-port=9222")
        
        # Set required capabilities
        chrome_options.set_capability("browserName", "chrome")
        chrome_options.set_capability("platformName", "windows")
        
        # Add experimental options
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option('w3c', True)
        
        # Initialize browser in a separate thread
        service = Service()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._init_driver,
            chrome_options,
            service
        )

    def _init_driver(self, options, service):
        try:
            self.driver = webdriver.Chrome(service=service, options=options)
            # Enable DevTools Protocol
            self.driver.execute_cdp_cmd('Network.enable', {})
            self.driver.execute_cdp_cmd('Page.enable', {})
            print("Chrome initialized successfully")
        except Exception as e:
            print(f"Error initializing Chrome: {e}")
            raise

    async def create_offer(self):
        try:
            self.pc = RTCPeerConnection()
            video_track = BrowserVideoStreamTrack(self.driver)
            self.pc.addTrack(video_track)
            
            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)
            
            return {
                "sdp": self.pc.localDescription.sdp,
                "type": self.pc.localDescription.type
            }
        except Exception as e:
            print(f"Error creating offer: {str(e)}")
            raise e

    async def handle_answer(self, answer):
        await self.pc.setRemoteDescription(
            RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
        )

    async def navigate_to(self, url: str):
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        await asyncio.get_event_loop().run_in_executor(None, self.driver.get, url)

    async def execute_command(self, command: str, params: dict):
        try:
            if command == "click":
                return await self._handle_click(params)
            elif command == "type":
                return await self._handle_type(params)
            elif command == "scroll":
                return await self._handle_scroll(params)
            else:
                return {"error": "Unknown command"}
        except Exception as e:
            return {"error": str(e)}

    async def _handle_click(self, params):
        x, y = params.get("x"), params.get("y")
        script = """
        const element = document.elementFromPoint(arguments[0], arguments[1]);
        if (element) {
            const rect = element.getBoundingClientRect();
            if (element.href) {
                // Check if URL is allowed before clicking
                const allowedDomains = ['google.com', 'github.com'];
                const url = new URL(element.href);
                if (!allowedDomains.some(domain => url.hostname.includes(domain))) {
                    return false;
                }
            }
            element.click();
            return true;
        }
        return false;
        """
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self.driver.execute_script,
            script,
            x,
            y
        )

    async def _handle_type(self, params):
        text = params.get("text", "")
        script = """
        const activeElement = document.activeElement;
        if (activeElement && 
            (activeElement.tagName === 'INPUT' || 
             activeElement.tagName === 'TEXTAREA' ||
             activeElement.contentEditable === 'true')) {
            activeElement.value = activeElement.value + arguments[0];
            return true;
        }
        return false;
        """
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self.driver.execute_script,
            script,
            text
        )

    async def _handle_scroll(self, params):
        x, y = params.get("x", 0), params.get("y", 0)
        script = f"window.scrollBy({x}, {y}); return true;"
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self.driver.execute_script,
            script
        )
