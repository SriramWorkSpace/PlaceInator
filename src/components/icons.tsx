import type { SVGProps } from "react";

/**
 * Google Material Symbols, outline style. Paths are copied verbatim; the only
 * change from the source markup is fill="currentColor" in place of a hardcoded
 * hex, so every icon inherits text color -- theme, active-nav accent, and
 * status colors (--success/--danger) all work without a second icon set.
 */
type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      height="20"
      width="20"
      viewBox="0 -960 960 960"
      fill="currentColor"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

/** Jobs -- searching for opportunities. */
export function SearchIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M380-320q-109 0-184.5-75.5T120-580q0-109 75.5-184.5T380-840q109 0 184.5 75.5T640-580q0 44-14 83t-38 69l224 224q11 11 11 28t-11 28q-11 11-28 11t-28-11L532-372q-30 24-69 38t-83 14Zm0-80q75 0 127.5-52.5T560-580q0-75-52.5-127.5T380-760q-75 0-127.5 52.5T200-580q0 75 52.5 127.5T380-400Z" />
    </Icon>
  );
}

/** Dashboard. */
export function HomeIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M240-200h120v-200q0-17 11.5-28.5T400-440h160q17 0 28.5 11.5T600-400v200h120v-360L480-740 240-560v360Zm-80 0v-360q0-19 8.5-36t23.5-28l240-180q21-16 48-16t48 16l240 180q15 11 23.5 28t8.5 36v360q0 33-23.5 56.5T720-120H560q-17 0-28.5-11.5T520-160v-200h-80v200q0 17-11.5 28.5T400-120H240q-33 0-56.5-23.5T160-200Zm320-270Z" />
    </Icon>
  );
}

/** Sidebar collapse/expand toggle. */
export function MenuIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M160-240q-17 0-28.5-11.5T120-280q0-17 11.5-28.5T160-320h640q17 0 28.5 11.5T840-280q0 17-11.5 28.5T800-240H160Zm0-200q-17 0-28.5-11.5T120-480q0-17 11.5-28.5T160-520h640q17 0 28.5 11.5T840-480q0 17-11.5 28.5T800-440H160Zm0-200q-17 0-28.5-11.5T120-680q0-17 11.5-28.5T160-720h640q17 0 28.5 11.5T840-680q0 17-11.5 28.5T800-640H160Z" />
    </Icon>
  );
}

/** Dismiss (error banners). */
export function CloseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M480-424 284-228q-11 11-28 11t-28-11q-11-11-11-28t11-28l196-196-196-196q-11-11-11-28t11-28q11-11 28-11t28 11l196 196 196-196q11-11 28-11t28 11q11 11 11 28t-11 28L536-480l196 196q11 11 11 28t-11 28q-11 11-28 11t-28-11L480-424Z" />
    </Icon>
  );
}

/** Settings nav item. */
export function SettingsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M433-80q-27 0-46.5-18T363-142l-9-66q-13-5-24.5-12T307-235l-62 26q-25 11-50 2t-39-32l-47-82q-14-23-8-49t27-43l53-40q-1-7-1-13.5v-27q0-6.5 1-13.5l-53-40q-21-17-27-43t8-49l47-82q14-23 39-32t50 2l62 26q11-8 23-15t24-12l9-66q4-26 23.5-44t46.5-18h94q27 0 46.5 18t23.5 44l9 66q13 5 24.5 12t22.5 15l62-26q25-11 50-2t39 32l47 82q14 23 8 49t-27 43l-53 40q1 7 1 13.5v27q0 6.5-2 13.5l53 40q21 17 27 43t-8 49l-48 82q-14 23-39 32t-50-2l-60-26q-11 8-23 15t-24 12l-13 66q-4 26-23.5 44T527-80h-94Zm7-80h79l14-106q31-8 57.5-23.5T639-327l99 41 39-68-86-65q5-14 7-29.5t2-31.5q0-16-2-31.5t-7-29.5l86-65-39-68-99 42q-22-23-48.5-38.5T533-694l-13-106h-79l-14 106q-31 8-57.5 23.5T321-633l-99-41-39 68 86 64q-5 15-7 30t-2 32q0 16 2 31t7 30l-86 65 39 68 99-42q22 23 48.5 38.5T427-266l13 106Zm42-180q58 0 99-41t41-99q0-58-41-99t-99-41q-59 0-99.5 41T342-480q0 58 40.5 99t99.5 41Zm-2-140Z" />
    </Icon>
  );
}

/** Status: connected / success. */
export function CheckCircleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m424-408-86-86q-11-11-28-11t-28 11q-11 11-11 28t11 28l114 114q12 12 28 12t28-12l226-226q11-11 11-28t-11-28q-11-11-28-11t-28 11L424-408Zm56 328q-83 0-156-31.5T197-197q-54-54-85.5-127T80-480q0-83 31.5-156T197-763q54-54 127-85.5T480-880q83 0 156 31.5T763-763q54 54 85.5 127T880-480q0 83-31.5 156T763-197q-54 54-127 85.5T480-80Zm0-80q134 0 227-93t93-227q0-134-93-227t-227-93q-134 0-227 93t-93 227q0 134 93 227t227 93Zm0-320Z" />
    </Icon>
  );
}

/** Outreach and Placement -- people/cohorts. */
export function GroupsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M280-240q-100 0-170-70T40-480q0-100 70-170t170-70h400q100 0 170 70t70 170q0 100-70 170t-170 70H280Zm0-80h400q66 0 113-47t47-113q0-66-47-113t-113-47H280q-66 0-113 47t-47 113q0 66 47 113t113 47Zm485-75q35-35 35-85t-35-85q-35-35-85-35t-85 35q-35 35-35 85t35 85q35 35 85 35t85-35Zm-285-85Z" />
    </Icon>
  );
}

/** Tailor -- requirement matched. */
export function CheckIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m382-434 338-338q12-12 28.5-12t28.5 12q12 12 12 28.5T777-715L410-348q-12 12-28 12t-28-12L183-519q-12-12-11.5-28.5T184-576q12-12 28.5-12t28.5 12l141 142ZM240-160q-17 0-28.5-11.5T200-200q0-17 11.5-28.5T240-240h480q17 0 28.5 11.5T760-200q0 17-11.5 28.5T720-160H240Z" />
    </Icon>
  );
}

/** Career -- learning resources, structured knowledge. */
export function BookIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M280-120q-33 0-56.5-23.5T200-200v-520q-17 0-28.5-11.5T160-760q0-17 11.5-28.5T200-800h160q0-17 11.5-28.5T400-840h160q17 0 28.5 11.5T600-800h160q17 0 28.5 11.5T800-760q0 17-11.5 28.5T760-720v520q0 33-23.5 56.5T680-120H280Zm400-600H280v520h400v-520ZM428.5-291.5Q440-303 440-320v-280q0-17-11.5-28.5T400-640q-17 0-28.5 11.5T360-600v280q0 17 11.5 28.5T400-280q17 0 28.5-11.5Zm160 0Q600-303 600-320v-280q0-17-11.5-28.5T560-640q-17 0-28.5 11.5T520-600v280q0 17 11.5 28.5T560-280q17 0 28.5-11.5ZM280-720v520-520Z" />
    </Icon>
  );
}

/** Resumes -- a formal document with an identity seal. */
export function ResumeDocIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M320-440h141q17 0 28.5-11.5T501-480q0-17-11.5-28.5T461-520H320q-17 0-28.5 11.5T280-480q0 17 11.5 28.5T320-440Zm0 160h141q17 0 28.5-11.5T501-320q0-17-11.5-28.5T461-360H320q-17 0-28.5 11.5T280-320q0 17 11.5 28.5T320-280Zm0-320h320q17 0 28.5-11.5T680-640q0-17-11.5-28.5T640-680H320q-17 0-28.5 11.5T280-640q0 17 11.5 28.5T320-600ZM200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h560q33 0 56.5 23.5T840-760v178q0 17-11.5 28.5T800-542q-17 0-28.5-11.5T760-582v-178H200v560h160q17 0 28.5 11.5T400-160q0 17-11.5 28.5T360-120H200Zm409-229q-29-29-29-71t29-71q29-29 71-29t71 29q29 29 29 71t-29 71q-29 29-71 29t-71-29Zm71 69q39 0 77.5 7.5T832-250q23 9 35.5 29.5T880-176v16q0 17-11.5 28.5T840-120H520q-17 0-28.5-11.5T480-160v-16q0-24 12.5-44.5T528-250q36-15 74.5-22.5T680-280Z" />
    </Icon>
  );
}

/** Profile indicator (top bar). */
export function PersonIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M367-527q-47-47-47-113t47-113q47-47 113-47t113 47q47 47 47 113t-47 113q-47 47-113 47t-113-47ZM160-240v-32q0-34 17.5-62.5T224-378q62-31 126-46.5T480-440q66 0 130 15.5T736-378q29 15 46.5 43.5T800-272v32q0 33-23.5 56.5T720-160H240q-33 0-56.5-23.5T160-240Zm80 0h480v-32q0-11-5.5-20T700-306q-54-27-109-40.5T480-360q-56 0-111 13.5T260-306q-9 5-14.5 14t-5.5 20v32Z" />
    </Icon>
  );
}

/** Theme toggle: currently dark, click for light. */
export function LightModeIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M480-360q50 0 85-35t35-85q0-50-35-85t-85-35q-50 0-85 35t-35 85q0 50 35 85t85 35ZM480-280q-83 0-141.5-58.5T280-480q0-83 58.5-141.5T480-680q83 0 141.5 58.5T680-480q0 83-58.5 141.5T480-280ZM200-440H40v-80h160v80Zm720 0H760v-80h160v80ZM440-760v-160h80v160h-80Zm0 720v-160h80v160h-80ZM256-650l-101-97 57-59 96 100-52 56Zm492 496-97-101 53-55 101 97-57 59Zm-98-550 97-101 59 57-100 96-56-52ZM154-212l101-97 55 53-97 101-59-57Z" />
    </Icon>
  );
}

/** Theme toggle: currently light, click for dark. */
export function DarkModeIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M484-80q-84 0-157.5-32t-128-86.5Q144-253 112-326.5T80-484q0-128 72-232t193-146q22-8 41 5.5t18 36.5q-3 85 27 162t90 137q60 60 137 90t162 27q26-1 38.5 17.5T863-345q-44 120-147.5 192.5T484-80Zm0-80q88 0 163-44t118-121q-86-8-163-43.5T464-465q-61-61-97-138t-43-163q-77 43-120.5 118.5T160-484q0 135 94.5 229.5T484-160Zm-20-305Z" />
    </Icon>
  );
}
