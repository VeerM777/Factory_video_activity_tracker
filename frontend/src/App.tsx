import { Routes, Route } from "react-router-dom";
import { UploadPage } from "./pages/UploadPage";
import { ReviewConsole } from "./pages/ReviewConsole";

function App() {
  return (
    <Routes>
      <Route path="/" element={<UploadPage />} />
      <Route path="/jobs/:jobId" element={<ReviewConsole />} />
    </Routes>
  );
}

export default App;
