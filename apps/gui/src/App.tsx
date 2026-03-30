import { AppShell } from "./components/shell/AppShell";
import { ShellProvider } from "./store/ShellProvider";

function App() {
  return (
    <ShellProvider>
      <AppShell />
    </ShellProvider>
  );
}

export default App;
