/**
 * Reference usage example, as originally supplied -- not routed into the
 * app. The real integration is DatePickerField, used by
 * src/routes/Jobs.tsx for the job deadline field, since a form needs the
 * selected value rather than a self-contained uncontrolled widget.
 */
import { Basic } from "@/components/ui/date-picker";

export default function DemoOne() {
  return <Basic />;
}
