import type { TransmissionLookup } from '@/types/chat'

interface TransmissionAudioModalProps {
  transmission: TransmissionLookup | null
  onClose: () => void
}

export function TransmissionAudioModal({
  transmission,
  onClose,
}: TransmissionAudioModalProps) {

  if (!transmission) return null

  const hasAudio = Boolean(transmission.audio_url && transmission.audio_path !== 'file not saved')
  const formattedDate = transmission.timestamp
    ? new Date(transmission.timestamp).toLocaleString()
    : 'Unknown'

  return (
    <div
      className="fixed inset-0 bg-black/65 backdrop-blur-xs flex items-center justify-center z-[60] p-4"
      onClick={onClose}
    >
      <div
        className="bg-[#181b26] border border-[#2e3347] rounded-lg shadow-2xl max-w-lg w-full overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-[#131620] border-b border-[#252836]">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 bg-indigo-900/60 border border-indigo-700/50 text-indigo-300 font-mono font-bold text-xs rounded">
              TX #{transmission.id}
            </span>
            <span className="text-sm font-semibold text-gray-200">
              {transmission.talkgroup || 'Unassigned Talkgroup'}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-100 text-lg leading-none p-1 cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-3.5 text-xs">
          <div className="flex justify-between text-gray-400 border-b border-[#252836] pb-2">
            <div>
              <span className="text-gray-500 mr-1">Time:</span>
              <span className="text-gray-300 font-mono">{formattedDate}</span>
            </div>
            <div>
              <span className="text-gray-500 mr-1">Duration:</span>
              <span className="text-gray-300 font-mono">
                {transmission.duration ? `${transmission.duration.toFixed(1)}s` : '—'}
              </span>
            </div>
          </div>

          {/* Transcript Box */}
          <div>
            <label className="block text-gray-400 font-medium mb-1 text-[11px] uppercase tracking-wider">
              Recorded Radio Transcription
            </label>
            <div className="bg-[#0f1118] p-3 rounded border border-[#232738] text-gray-200 font-mono leading-relaxed select-text">
              {transmission.transcript || <span className="text-gray-500 italic">No transcript recorded</span>}
            </div>
          </div>

          {/* Audio Player */}
          <div>
            <label className="block text-gray-400 font-medium mb-1 text-[11px] uppercase tracking-wider">
              Audio Transmission Playback
            </label>
            {hasAudio ? (
              <div className="bg-[#11141e] p-2 rounded border border-[#232738]">
                <audio
                  controls
                  autoPlay
                  src={transmission.audio_url}
                  className="w-full h-8"
                />
              </div>
            ) : (
              <div className="p-2 bg-[#1a1717] border border-[#3d2525] rounded text-gray-400 italic">
                Audio recording was not retained for this transmission.
              </div>
            )}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-4 py-3 bg-[#131620] border-t border-[#252836] text-xs">
          <a
            href={`/dashboard`}
            className="text-indigo-400 hover:text-indigo-300 hover:underline"
          >
            Open Live Audio Feed
          </a>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 bg-[#25293a] hover:bg-[#30354b] text-gray-200 rounded font-medium cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
