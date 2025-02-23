import React, { useState, useRef, useEffect } from 'react';

const BrowserSession: React.FC = () => {
    const [isConnected, setIsConnected] = useState<boolean>(false);
    const videoRef = useRef<HTMLVideoElement>(null);
    const peerConnection = useRef<RTCPeerConnection | null>(null);
    const wsRef = useRef<WebSocket | null>(null);

    const startSession = async () => {
        try {
            await initializeWebRTC();
            await setupWebSocket();
        } catch (error) {
            console.error('Failed to start session:', error);
        }
    };

    const initializeWebRTC = async () => {
        try {
            const pc = new RTCPeerConnection({
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' },
                    { urls: 'stun:stun1.l.google.com:19302' }
                ]
            });

            pc.onicecandidate = (event) => {
                console.log("ICE candidate:", event.candidate);
            };

            pc.onconnectionstatechange = () => {
                console.log("Connection state:", pc.connectionState);
                if (pc.connectionState === 'connected') {
                    console.log("WebRTC connected successfully");
                }
            };

            pc.ontrack = (event) => {
                console.log("Received track:", event.track.kind);
                if (videoRef.current && event.streams[0]) {
                    console.log("Setting video stream");
                    videoRef.current.srcObject = event.streams[0];
                    videoRef.current.onloadedmetadata = () => {
                        console.log("Video metadata loaded");
                        videoRef.current?.play().catch(console.error);
                    };
                }
            };

            // Get offer from server
            const response = await fetch('http://localhost:8000/webrtc/offer');
            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}`);
            }
            
            const offer = await response.json();
            console.log("Received offer:", offer);
            await pc.setRemoteDescription(new RTCSessionDescription(offer));

            // Create and send answer
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            
            const answerResponse = await fetch('http://localhost:8000/webrtc/answer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sdp: answer.sdp,
                    type: answer.type
                })
            });

            if (!answerResponse.ok) {
                throw new Error(`Server responded with ${answerResponse.status}`);
            }

            peerConnection.current = pc;
            setIsConnected(true);
        } catch (error) {
            console.error("WebRTC initialization failed:", error);
            setIsConnected(false);
        }
    };

    const setupWebSocket = async () => {
        try {
            const response = await fetch('http://localhost:8000/launch/www.google.com');
            const data = await response.json();
            
            if (data.status === 'success') {
                const ws = new WebSocket('ws://localhost:8000/ws/browser');
                
                ws.onopen = () => {
                    setIsConnected(true);
                };

                ws.onclose = () => {
                    setIsConnected(false);
                };

                wsRef.current = ws;
            }
        } catch (error) {
            console.error('Failed to setup WebSocket:', error);
        }
    };

    const handleMouseClick = (e: React.MouseEvent<HTMLDivElement>) => {
        if (!videoRef.current || !wsRef.current) return;
        
        const rect = videoRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        wsRef.current.send(JSON.stringify({
            command: 'click',
            params: { x, y }
        }));
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (!wsRef.current) return;
        
        wsRef.current.send(JSON.stringify({
            command: 'type',
            params: { text: e.key }
        }));
        
        e.preventDefault();
    };

    const handlePaste = async (e: React.ClipboardEvent) => {
        if (!wsRef.current) return;
        
        const text = e.clipboardData.getData('text');
        wsRef.current.send(JSON.stringify({
            command: 'type',
            params: { text }
        }));
        
        e.preventDefault();
    };

    useEffect(() => {
        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
            if (peerConnection.current) {
                peerConnection.current.close();
            }
        };
    }, []);

    return (
        <div className="browser-session">
            <button 
                onClick={startSession}
                disabled={isConnected}
            >
                {isConnected ? 'Session Active' : 'Start Session'}
            </button>
            
            {isConnected && (
                <div className="browser-view">
                    <video
                        ref={videoRef}
                        autoPlay
                        playsInline
                        muted
                        style={{
                            width: '1024px',
                            height: '768px',
                            backgroundColor: '#fff',
                            objectFit: 'cover'
                        }}
                    />
                </div>
            )}
        </div>
    );
};

export default BrowserSession;
