import SectionCard from "./SectionCard";
import { useProfileDispatch, useProfileState } from "../ProfileContext";

const INPUT_CLASS =
  "w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

export default function SelfEvaluationSection() {
  const { self_evaluation } = useProfileState();
  const dispatch = useProfileDispatch();

  return (
    <SectionCard title="自我评价">
      <textarea
        rows={5}
        value={self_evaluation}
        onChange={(e) =>
          dispatch({ type: "SET_SELF_EVAL", value: e.target.value })
        }
        className={INPUT_CLASS}
        placeholder="介绍一下你自己…"
      />
    </SectionCard>
  );
}
