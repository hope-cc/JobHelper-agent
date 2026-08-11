import { useAppState } from "../AppContext";
import WelcomeScreen from "./WelcomeScreen";
import ChatView from "./ChatView";
import ResumePage from "./ResumePage";
import PlaceholderPage from "./PlaceholderPage";
import ProfilePage from "./ProfilePage";

export default function MainArea() {
  const { view } = useAppState();

  switch (view) {
    case "new_chat":
      return (
        <main className="flex-1 h-full">
          <WelcomeScreen />
        </main>
      );
    case "conversation":
      return (
        <main className="flex-1 h-full">
          <ChatView />
        </main>
      );
    case "resume":
      return (
        <main className="flex-1 h-full">
          <ResumePage />
        </main>
      );
    case "progress":
      return (
        <main className="flex-1 h-full">
          <PlaceholderPage title="投递进度" />
        </main>
      );
    case "profile":
      return (
        <main className="flex-1 h-full">
          <ProfilePage />
        </main>
      );
    default:
      return null;
  }
}
