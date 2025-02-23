import React from 'react';
import WebRTCStream from './components/WebRtcStream';
import './App.css';

const App: React.FC = () => {
  return (
    <div className="App">
      <h1>Selenium Browser Stream</h1>
      <WebRTCStream wsUrl="http://localhost:8000" />
    </div>
  );
};

export default App;