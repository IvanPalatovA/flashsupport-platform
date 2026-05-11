import React, { useState } from 'react';

interface ProactivePromptProps {
  message: string;
  options: string[];
  onAccept: () => void;
  onDecline: () => void;
}

export const ProactivePrompt: React.FC<ProactivePromptProps> = ({ message, options, onAccept, onDecline }) => {
  const [visible, setVisible] = useState(true);

  if (!visible) return null;

  return (
    <div className="fixed bottom-4 right-4 bg-white p-4 rounded-lg shadow-lg border border-gray-200 w-72 z-50">
      <p className="text-sm text-gray-800 mb-3">{message}</p>
      <div className="flex flex-col gap-2">
        {options.map((opt, i) => (
          <button
            key={i}
            onClick={() => { setVisible(false); i === 0 ? onAccept() : onDecline(); }}
            className={`px-3 py-2 rounded text-sm ${i === 0 ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  );
};