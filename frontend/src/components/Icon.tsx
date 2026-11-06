import {
  Activity, Briefcase, Building2, Cable, Cctv, Factory, Globe, HardDrive, LifeBuoy, Mail, MessageCircle,
  MessageSquareText, Network, Package, Phone, PhoneCall, Pill, Pin, QrCode, RotateCcw, Send, RadioTower, Router, Scissors,
  Shield, ShieldCheck, Smartphone, Stethoscope, Store, Truck, UtensilsCrossed, Wifi, type LucideIcon,
} from "lucide-react";

// Icon names come from the backend (Lucide names), so the API decides which picture a product gets.
const MAP: Record<string, LucideIcon> = {
  router: Router, "radio-tower": RadioTower, cable: Cable, smartphone: Smartphone, "life-buoy": LifeBuoy,
  network: Network, pin: Pin, "phone-call": PhoneCall, phone: Phone, "message-square-text": MessageSquareText,
  "message-circle": MessageCircle, mail: Mail, "hard-drive": HardDrive, globe: Globe, "qr-code": QrCode,
  "shield-check": ShieldCheck, shield: Shield, wifi: Wifi, cctv: Cctv, activity: Activity, truck: Truck,
  store: Store, scissors: Scissors, pill: Pill, stethoscope: Stethoscope, utensils: UtensilsCrossed,
  briefcase: Briefcase, factory: Factory, building: Building2, "rotate-ccw": RotateCcw, send: Send,
};

export function Icon({ name, size = 22 }: { name: string; size?: number }) {
  const C = MAP[name] ?? Package;
  return <C size={size} strokeWidth={1.9} aria-hidden="true" />;
}
