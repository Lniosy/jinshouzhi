/**
 * VIP / license gate hook template (Android Java).
 *
 * Fill TARGETS, then PID-attach from the repo root:
 *   frida-safe-android/scripts/safe-attach.sh <package> vip-license-re/scripts/frida-vip-hooks.js
 *
 * Only hook app-owned classes. Do not hook Android framework services.
 * Local-feature apps: force VIP gates even if a free login wall exists.
 * Login first when free; do not stop at "needs account". Block sync writers that reset FREE.
 */

'use strict';

const TARGETS = [
  // { className: 'com.example.app.VipManager', methods: ['isVip', 'isPremium', 'checkLicense'] },
  // { className: 'com.example.app.LicenseHelper', methods: ['verify', 'validate'] },
];

const FORCE_TRUE_METHODS = new Set([
  'isVip',
  'isVIP',
  'isPremium',
  'isMember',
  'isPro',
  'checkLicense',
  'verifyLicense',
  'hasLicense',
  'isActivated',
  'isUnlock',
  'isUnlocked',
]);

function hookMethod(cls, methodName) {
  if (!cls[methodName]) {
    console.log('[-] missing method: ' + cls.$className + '.' + methodName);
    return;
  }
  cls[methodName].overloads.forEach(function (ov) {
    ov.implementation = function () {
      const args = [];
      for (let i = 0; i < arguments.length; i++) args.push(arguments[i]);
      let ret;
      try {
        ret = ov.apply(this, arguments);
      } catch (e) {
        console.log('[!] ' + methodName + ' threw: ' + e);
        throw e;
      }
      const force = FORCE_TRUE_METHODS.has(methodName);
      console.log(
        '[gate] ' +
          cls.$className +
          '.' +
          methodName +
          '(' +
          args.map(String).join(', ') +
          ') => ' +
          ret +
          (force ? ' -> true' : '')
      );
      if (force) return true;
      return ret;
    };
  });
  console.log('[+] hooked ' + cls.$className + '.' + methodName);
}

Java.perform(function () {
  if (!TARGETS.length) {
    console.log('[!] TARGETS is empty. Fill class/method names from static analysis first.');
    return;
  }
  TARGETS.forEach(function (t) {
    try {
      const cls = Java.use(t.className);
      (t.methods || []).forEach(function (m) {
        hookMethod(cls, m);
      });
    } catch (e) {
      console.log('[-] class not found: ' + t.className + ' (' + e + ')');
    }
  });
});
