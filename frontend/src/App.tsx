import { useCallback, useState } from "react";
import "./App.css";
import Upload from "./components/Upload";
import Calibration from "./components/Calibration";
import Processing from "./components/Processing";
import Dashboard from "./components/Dashboard";
import History from "./components/History";
import PlayersPage from "./components/PlayersPage";
import { getMatch } from "./api";
import type { MatchStatus } from "./types";

type Stage = "upload" | "calibrate" | "processing" | "dashboard" | "players";

function stageFor(status: MatchStatus): Stage {
  if (status === "awaiting_calibration") return "calibrate";
  if (status === "done") return "dashboard";
  return "processing";
}

function App() {
  const [matchId, setMatchId] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("upload");
  const [historyKey, setHistoryKey] = useState(0);
  const [profileFocus, setProfileFocus] = useState<string | null>(null);

  async function selectMatch(id: string) {
    const meta = await getMatch(id);
    setMatchId(id);
    setStage(stageFor(meta.status));
  }

  function reset() {
    setMatchId(null);
    setStage("upload");
    setHistoryKey((k) => k + 1);
  }

  const onProcessed = useCallback((status: MatchStatus) => {
    setStage(stageFor(status));
    setHistoryKey((k) => k + 1);
  }, []);

  const refreshHistory = useCallback(() => setHistoryKey((k) => k + 1), []);

  return (
    <div className="app">
      <header>
        <h1>Minifootball Stats</h1>
        <p className="tagline">Upload a match, mark the pitch once, get stats, clips and coaching feedback.</p>
        <nav className="nav">
          <button className={stage !== "players" ? "active" : ""} onClick={() => (matchId ? selectMatch(matchId) : reset())}>
            Matches
          </button>
          <button
            className={stage === "players" ? "active" : ""}
            onClick={() => {
              setProfileFocus(null);
              setStage("players");
            }}
          >
            Players
          </button>
          {matchId && (
            <button onClick={reset} title="upload a new match video">
              + New match
            </button>
          )}
        </nav>
      </header>

      <div className="layout">
        <main>
          {stage === "upload" && (
            <Upload
              onUploaded={(id) => {
                setMatchId(id);
                setStage("processing");
                setHistoryKey((k) => k + 1);
              }}
            />
          )}
          {stage === "processing" && matchId && <Processing matchId={matchId} onFinished={onProcessed} />}
          {stage === "calibrate" && matchId && (
            <Calibration matchId={matchId} onCalibrated={() => setStage("processing")} />
          )}
          {stage === "dashboard" && matchId && (
            <Dashboard
              key={matchId}
              matchId={matchId}
              onRecalibrate={() => setStage("calibrate")}
              onRenamed={refreshHistory}
              onOpenProfile={(name) => {
                setProfileFocus(name);
                setStage("players");
              }}
            />
          )}
          {stage === "players" && <PlayersPage key={profileFocus ?? ""} focus={profileFocus} onOpenMatch={selectMatch} />}
        </main>

        <aside>
          <History
            onSelect={selectMatch}
            refreshKey={historyKey}
            onDeleted={(id) => {
              if (id === matchId) reset();
            }}
          />
        </aside>
      </div>
    </div>
  );
}

export default App;
