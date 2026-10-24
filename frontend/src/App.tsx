import { useState } from "react";
import "./App.css";
import Upload from "./components/Upload";
import Calibration from "./components/Calibration";
import Processing from "./components/Processing";
import Dashboard from "./components/Dashboard";
import History from "./components/History";
import { getMatch } from "./api";

type Stage = "upload" | "calibrate" | "processing" | "dashboard";

function App() {
  const [matchId, setMatchId] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("upload");
  const [historyKey, setHistoryKey] = useState(0);

  async function selectMatch(id: string) {
    const meta = await getMatch(id);
    setMatchId(id);
    if (meta.status === "awaiting_calibration") setStage("calibrate");
    else if (meta.status === "done") setStage("dashboard");
    else setStage("processing");
  }

  function reset() {
    setMatchId(null);
    setStage("upload");
    setHistoryKey((k) => k + 1);
  }

  return (
    <div className="app">
      <header>
        <h1>Minifootball Stats</h1>
        <p className="tagline">Upload a match, calibrate the pitch, get player/team stats.</p>
        {matchId && (
          <button className="link-button" onClick={reset}>
            + Analyze another video
          </button>
        )}
      </header>

      <div className="layout">
        <main>
          {stage === "upload" && (
            <Upload
              onUploaded={(id) => {
                setMatchId(id);
                setStage("calibrate");
              }}
            />
          )}
          {stage === "calibrate" && matchId && (
            <Calibration matchId={matchId} onCalibrated={() => setStage("processing")} />
          )}
          {stage === "processing" && matchId && (
            <Processing
              matchId={matchId}
              onDone={() => {
                setStage("dashboard");
                setHistoryKey((k) => k + 1);
              }}
            />
          )}
          {stage === "dashboard" && matchId && <Dashboard matchId={matchId} />}
        </main>

        <aside>
          <History onSelect={selectMatch} refreshKey={historyKey} />
        </aside>
      </div>
    </div>
  );
}

export default App;
