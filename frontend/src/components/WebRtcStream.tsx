import React, { useEffect, useRef, useState } from 'react';

interface WebRTCStreamProps {
  wsUrl?: string;
}

const WebRTCStream: React.FC<WebRTCStreamProps> = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const initWebRTC = async () => {
      try {
        // Create RTCPeerConnection
        const pc = new RTCPeerConnection({
          iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
        });
        peerConnectionRef.current = pc;

        // Add transceiver for receiving video only
        pc.addTransceiver('video', { direction: 'recvonly' });

        // Handle ICE candidates
        pc.onicecandidate = async (event) => {
          if (event.candidate) {
            try {
              await fetch('http://localhost:8000/webrtc/ice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(event.candidate)
              });
            } catch (err) {
              console.error('Error sending ICE candidate:', err);
            }
          }
        };

        // Handle connection state changes
        pc.onconnectionstatechange = () => {
          console.log('Connection state:', pc.connectionState);
          setIsConnected(pc.connectionState === 'connected');
        };

        // Handle incoming tracks
        pc.ontrack = (event) => {
          if (videoRef.current && event.streams[0]) {
            videoRef.current.srcObject = event.streams[0];
          }
        };

        // Create and send offer
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        const response = await fetch('http://localhost:8000/webrtc/offer', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Accept': 'application/json'
          },
          credentials: 'include',
          body: JSON.stringify({
            sdp: offer.sdp,
            type: offer.type,
          })
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const answer = await response.json();
        if (!answer.sdp || !answer.type) {
          throw new Error('Invalid answer format received from server');
        }

        await pc.setRemoteDescription(new RTCSessionDescription(answer));
        setIsConnected(true);

      } catch (err) {
        console.error('WebRTC initialization failed:', err);
        setError(err instanceof Error ? err.message : 'Failed to initialize WebRTC');
        setIsConnected(false);
      }
    };

    initWebRTC();

    return () => {
      if (peerConnectionRef.current) {
        peerConnectionRef.current.close();
      }
    };
  }, []);

  return (
    <div className="webrtc-stream">
      {error && <div className="error">Error: {error}</div>}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        style={{
          width: '1024px',
          height: '768px',
          backgroundColor: '#000',
          display: isConnected ? 'block' : 'none'
        }}
      />
      {!isConnected && !error && (
        <div>Connecting to stream...</div>
      )}
    </div>
  );
};

export default WebRTCStream;