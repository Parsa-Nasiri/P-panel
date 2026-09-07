import { InlineKeyboard, Keyboard } from "grammy";
import { fa } from "@proxy/shared";

/** Persistent main menu (reply / "outline" keyboard), Persian. */
export function mainMenu(): Keyboard {
  return new Keyboard()
    .text(fa.buy).text(fa.trial).row()
    .text(fa.myConfigs).text(fa.paymentGuide).row()
    .text(fa.support).text(fa.help)
    .placeholder("یک گزینه انتخاب کنید…").resized();
}

export function planList(plans: { id: string; name: string; priceCents: number; gaming: boolean }[]): InlineKeyboard {
  const kb = new InlineKeyboard();
  for (const p of plans) {
    kb.text(`${p.gaming ? "🎮 " : ""}${p.name} — ${Math.round(p.priceCents / 100)} تومان`, `plan:${p.id}`).row();
  }
  return kb.row().text(fa.cancel, "cancel");
}

export function planActions(planId: string): InlineKeyboard {
  return new InlineKeyboard()
    .text(fa.sendReceipt, `receipt:${planId}`).primary()
    .row().text(fa.cancel, "cancel");
}

export function orderCardButtons(orderId: string): InlineKeyboard {
  return new InlineKeyboard()
    .text(fa.approveBtn, `approve:${orderId}`).success()
    .text(fa.rejectBtn, `reject:${orderId}`).danger()
    .row().text("👤 پروفایل", `profile:${orderId}`);
}

export function subActions(subId: string, hasDns: boolean): InlineKeyboard {
  const kb = new InlineKeyboard()
    .text(fa.getLink, `link:${subId}`).primary()
    .text(fa.getQr, `qr:${subId}`)
    .row()
    .text(fa.getUsage, `usage:${subId}`)
    .text(fa.rename, `rename:${subId}`);
  if (hasDns) kb.row().text(fa.getDns, `dns:${subId}`);
  return kb.row().text(fa.back, "back_main");
}

export function backToMenu(): InlineKeyboard {
  return new InlineKeyboard().text(fa.back, "back_main");
}
