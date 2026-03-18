# APK Security Analysis Report

## APK Information
| Property | Value |
|----------|-------|
| **Package Name** | `com.whitebit.android` |
| **App Name** | WhiteBIT |
| **Version Name** | 3.70.0 |
| **Version Code** | 30000393 |
| **Min SDK Version** | 24 (Android 7.0) |
| **Target SDK Version** | 36 (Android 16) |
| **Source URL** | https://whitelabel-cdn-prod.digitalturbine.com/files/26b417db-95ee-4530-91ed-baac8a75cab7.apks |

---

## 1. Play Integrity Check

### Status: ✅ PRESENT AND ACTIVE

### Findings:

#### Play Integrity API Library Integration
The app includes the Google Play Integrity API library at version **1.4.0** (based on source annotation in smali files).

**Key classes found:**
- `com.google.android.play.core.integrity.IntegrityManager`
- `com.google.android.play.core.integrity.IntegrityManagerFactory`
- `com.google.android.play.core.integrity.IntegrityTokenRequest`
- `com.google.android.play.core.integrity.IntegrityTokenResponse`
- `com.google.android.play.core.integrity.StandardIntegrityManager`

#### Active Usage Locations:

1. **AppsFlyer SDK Integration** (`com.appsflyer.internal.AFj1kSDK`)
   - Uses `IntegrityManagerFactory.create(Context)` to create integrity manager
   - Data class `AFi1jSDK` includes `PlayIntegrityApiData` field with timestamp
   - Has endpoints for Play Integrity reporting:
     - `getPlayIntegrityUrl()`
     - `getUrlForPlayIntegrityReporting()`

2. **reCAPTCHA Integration** (`com.google.android.recaptcha.internal`)
   - Uses `IntegrityManagerFactory.createStandard(Context)` for Standard API
   - Classes: `zzdp.smali`, `zzbo.smali`, `zzbl.smali`, `zzbd.smali`

### Conclusion:
The app actively implements Google Play Integrity API through:
- AppsFlyer SDK for fraud detection and attribution
- reCAPTCHA for bot protection

---

## 2. Wakelock Check

### Status: ✅ PERMISSION DECLARED AND ACTIVELY USED

### Manifest Permission:
```xml
<uses-permission android:name="android.permission.WAKE_LOCK"/>
```
Location: Line 80 in AndroidManifest.xml

### Wakelock Usage Locations:

| Component | Wakelock Name | Type | Purpose |
|-----------|---------------|------|---------|
| **Zendesk Talk SDK** | `talk_sdk:proximity_lock` | Proximity | Voice call screen control |
| **Firebase Messaging** | `wake:com.google.firebase.messaging` | Partial (1) | FCM topic sync |
| **Firebase Messaging** | `fiid-sync` | Partial (1) | Firebase Instance ID sync |
| **Notifee** | `Notifee:lock` | Screen Bright + Full (0x3000001a) | Notification display |
| **Notifee** | `Notifee:cpuLock` | Partial (1) | CPU wake for notifications |
| **React Native** | HeadlessJsTaskService | Partial (1) | Background JS task execution |
| **ExoPlayer** | `ExoPlayer:WakeLockManager` | Partial (1) | Media playback |
| **AndroidX Work** | Various (ProcessCommand, etc.) | Partial (1) | WorkManager background tasks |
| **Google GMS** | GMS Stats WakeLock | Partial | Analytics/measurement |

### Wakelock Release Analysis:

| Library | Acquire Count | Release Count | Status |
|---------|---------------|---------------|--------|
| Zendesk Talk | 1 | 1 | ✅ Properly released |
| Firebase Messaging | 2 | 9 | ✅ Properly released |
| GMS Stats | 1 | 1 | ✅ Properly released |
| React Native HeadlessJS | 1 | 1 | ✅ Properly released |
| AndroidX Work | 4 | 7 | ✅ Properly released |
| ExoPlayer | 1 | 1 | ✅ Properly released |
| Notifee | 2 | 0 (in visible code) | ⚠️ Not visible in analyzed scope |

### Potential Concerns:

1. **Notifee Wakelocks**: The Notifee library acquires two wakelocks (`Notifee:lock` and `Notifee:cpuLock`) but the release calls were not found in the immediate scope. This is common for notification handling libraries where release happens in callbacks.

2. **Multiple Wakelock Sources**: The app has multiple independent wakelock implementations from various SDKs, which is normal for a complex app with:
   - Push notifications (Firebase, Notifee)
   - Voice calls (Zendesk Talk)
   - Media playback (ExoPlayer)
   - Background tasks (WorkManager, React Native)

---

## Summary

| Check | Status | Details |
|-------|--------|---------|
| **Play Integrity** | ✅ Active | Integrated via AppsFlyer SDK and reCAPTCHA |
| **Wakelock Permission** | ✅ Declared | `android.permission.WAKE_LOCK` in manifest |
| **Wakelock Usage** | ✅ Present | Multiple legitimate use cases across 8+ libraries |
| **Wakelock Release** | ⚠️ Mostly Verified | Most wakelocks have corresponding releases; Notifee release not visible in analyzed scope |

---

## Technical Details

### Files Analyzed
- `AndroidManifest.xml` - Permissions and components
- `smali_classes*/` - Decompiled DEX files (8 classes.dex files)
- `apktool.yml` - APK metadata

### Analysis Date
March 18, 2026

### Tools Used
- apktool 2.7.0
- grep/ripgrep for code pattern analysis
