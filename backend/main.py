import logging
from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import asyncio
import json
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, MediaStreamTrack, RTCRtpSender, RTCIceCandidate  # Add RTCIceCandidate
from aiortc.mediastreams import MediaStreamError
import av
import numpy as np
from typing import Optional
import cv2  # new import
from fractions import Fraction  # new import
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Suppress TF warnings

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Update CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Browser:
    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None
        self.pc: Optional[RTCPeerConnection] = None

    async def initialize(self):
        try:
            if self.driver:
                self.driver.quit()
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # enable headless mode for faster startup
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1280,720")  # lower resolution for faster capture
            chrome_options.add_argument("--disable-gpu")
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.get("https://google.com")
            logger.info("Browser initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise

    async def cleanup(self):
        if self.pc:
            await self.pc.close()
        if self.driver:
            self.driver.quit()

class BrowserVideoStreamTrack(VideoStreamTrack):
    kind = "video"  # Explicitly set the kind

    def __init__(self, browser: Browser):
        super().__init__()
        self.browser = browser
        self.frame_count = 0

    async def recv(self):
        try:
            if not self.browser.driver:
                logger.error("Browser driver is not initialized")
                raise MediaStreamError("Browser driver not initialized")

            # Capture screenshot and decode PNG to an image array
            screenshot = self.browser.driver.get_screenshot_as_png()
            if not screenshot:
                logger.error("Failed to capture screenshot")
                raise MediaStreamError("Screenshot capture failed")

            nparr = np.frombuffer(screenshot, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                logger.error("Failed to decode image")
                raise MediaStreamError("Image decode failed")

            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            frame = av.VideoFrame.from_ndarray(img, format='rgb24')
            frame.pts = self.frame_count
            frame.time_base = Fraction(1, 30)
            self.frame_count += 1
            
            # Remove or reduce sleep for near real-time update:
            await asyncio.sleep(0.001)  # minimal delay; adjust as needed or remove entirely
            return frame
        except Exception as e:
            logger.error(f"Error capturing frame: {e}", exc_info=True)
            raise MediaStreamError(f"Failed to capture frame: {str(e)}")

browser = Browser()

@app.on_event("startup")
async def startup_event():
    await browser.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    await browser.cleanup()

@app.post("/webrtc/offer")
async def webrtc_offer(request: Request):
    try:
        offer = await request.json()
        logger.info(f"Received offer: {offer}")
        
        if browser.pc:
            await browser.pc.close()
        
        browser.pc = RTCPeerConnection()
        
        @browser.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state changed: {browser.pc.connectionState}")
        
        # Prepare video track and add a transceiver to ensure a video m-line exists.
        video_track = BrowserVideoStreamTrack(browser)
        transceiver = browser.pc.addTransceiver("video", direction="sendonly")
        transceiver.sender.replaceTrack(video_track)
        
        # Set remote description and create answer.
        await browser.pc.setRemoteDescription(
            RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
        )
        answer = await browser.pc.createAnswer()
        await browser.pc.setLocalDescription(answer)
        
        if not browser.pc.localDescription:
            raise ValueError("Local description not set")
            
        logger.info(f"Sending answer: {browser.pc.localDescription}")
        return {
            "sdp": browser.pc.localDescription.sdp,
            "type": browser.pc.localDescription.type
        }
    except Exception as e:
        logger.error(f"Error in webrtc_offer: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webrtc/ice")
async def webrtc_ice(candidate: dict):
    if browser.pc:
        try:
            ice_candidate = RTCIceCandidate(
                sdpMid=candidate.get("sdpMid"),
                sdpMLineIndex=candidate.get("sdpMLineIndex"),
                candidate=candidate.get("candidate")
            )
            await browser.pc.addIceCandidate(ice_candidate)
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Error adding ICE candidate: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    return {"status": "no peer connection"}

@app.get("/health")
async def health_check():
    if not browser.driver:
        raise HTTPException(status_code=500, detail="Browser not initialized")
    try:
        # Try to take a test screenshot
        browser.driver.get_screenshot_as_png()
        return {"status": "healthy"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Browser not responding: {str(e)}")