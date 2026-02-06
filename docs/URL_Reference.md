# Site Controller URL Reference Guide

**Version:** 2.00.01  
**Date:** April 22, 2016  
**Company:** Verifone, Inc.

---

## Table of Contents

1. [Introduction](#1-introduction)
   - [Glossary of Terms](#glossary-of-terms)
   - [Informational Functions](#informational-functions)
   - [Credential Management Functions](#credential-management-functions)
2. [Reports](#2-reports)
3. [Maintenance Functions](#3-maintenance-functions)
4. [Event Notification](#4-event-notification)
5. [Deprecated Commands](#5-deprecated-commands)
6. [NAXML APIs](#6-naxml-apis)

---

## 1. Introduction

The Site Controller URL Reference provides a detailed reference for using the Hyper-Text Transfer Protocol (HTTP) for performing Site Controller maintenance and reporting functions.

### Glossary of Terms

| Term | URL Syntax | Definition |
|------|-----------|------------|
| **Site Controller** | `{site-controller_IP}` | A generic term for Sapphire and Commander and applies to both. |
| **Commander** | `{commander_IP}` | The new generation of the Verifone Site Controller. Operates with Ruby2 and Topaz POS workstations. |
| **Sapphire** | `{sapphire_IP}` | The legacy generation of the Verifone Site Controller. Operates with Ruby SuperSystem and Topaz workstations. |

> **Note:** For URLs with more than one format, alternate URLs are listed. For readability, URLs are presented on two lines, but are entered as one continuous string.

---

## Informational Functions

### vAppInfo

**Description:** View the document that describes the NewPro and GemPro applications currently active on Site Controller.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vAppInfo
```

**Locator:**
- XML Schema Document: `vsmsConfigData.xsd`
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `appInfo`

---

## Credential Management Functions

### validate

**Description:** Given a user name and a password, return a credential from the Site Controller that allows access to other system functions.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=validate&user={user}&passwd={passwd}
```

**Usage:**
- `user`: User Name
- `passwd`: Password

**Locator:**
- XML Schema Document: `credential.xsd`
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `credential`

> **Important:** Do not request more than one "cookie" per login even in a multi-threaded application; share the cookie across the threads. Best practice is to release the credential when it is no longer required; the system has a maximum of five cookies in use at a given time.

### ufunctionlist

**Description:** Given a cookie, return an updated credential from the Site Controller.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=ufunctionlist&cookie={cookie}
```

**Usage:**
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `credential.xsd`
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `credential`

### releaseCredential

**Description:** Release and remove the credential associated with the designated cookie.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=releaseCredential&cookie={cookie}
```

**Usage:**
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `RPC.xsd`
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `Response`

---

## 2. Reports

### Retrieving Report Availability Lists

#### vtlogpdlist

**Description:** Get a list of all transaction logs (by period: 1, 2) available for all period types.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vtlogpdlist&cookie={cookie}
```

**Usage:**
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: none
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `periodList`

#### vcashierpdlist

**Description:** Get a list of all the cashier report periods the currently signed in user can access.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vcashierpdlist&cookie={cookie}
```

#### vpayrollpdlist2

**Description:** Get a list of all the payroll report periods available.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vpayrollpdlist2&cookie={cookie}
```

#### vcwpaypointpdlist

**Description:** Get a list of all the car wash pay point report periods available.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vcwpaypointpdlist&cookie={cookie}
```

#### vreportpdlist

**Description:** Get a list of available reports for all vrubyrept reports (period: 1-4).

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vreportpdlist&cookie={cookie}
```

#### vviperpdList

**Description:** Get a list of all viper report periods available.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vviperpdlist&cookie={cookie}
```

> **Note:** Only use the `vs:period/@sysid='2'` entries when requesting Viper reports (vviperrept)

---

### Viewing VIPER Reports

#### vviperrept/batchTotals

**Description:** View viper batch totals for a specific terminal batch and FEP.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vviperrept&reptname=batchTotals&fepname={fepname}&terminalbatchnum={terminalbatchnum}&cookie={cookie}
```

**Usage:**
- `fepname`: Use value returned by vviperpdlist (vs:period/@sysid='2')
- `terminalbatchnum`: Use value returned by vviperpdlist (vs:period/@sysid='2')
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `reportData.xsd`
- Namespace: `urn:vfi-viper.nwbasetypes.2011-05-09`
- Root element: `reportData`

#### vviperrept/loyaltyTotals

**Description:** View viper loyalty totals for a specific terminal batch and FEP.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vviperrept&reptname=loyaltyTotals&fepname={fepname}&terminalbatchnum={terminalbatchnum}&cookie={cookie}
```

#### vviperrept/paymentTotals

**Description:** View viper payment totals (Terminal, Host and Card Type) for a specific terminal batch and FEP.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vviperrept&reptname=paymentTotals&fepname={fepname}&terminalbatchnum={terminalbatchnum}&cookie={cookie}
```

#### vviperrept/prepaidTotals

**Description:** View viper prepaid totals for a specific terminal batch and FEP.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vviperrept&reptname=prepaidTotals&fepname={fepname}&terminalbatchnum={terminalbatchnum}&cookie={cookie}
```

---

### Viewing Reports Based on Transaction Logs

> **PA-DSS Compliance Note:** If the software is PA-DSS compliant, the commands "vperiodrept" and "vperiodreptz" will return an "X" for the account number and expiration date in the Transaction Log. Use the "vperiodrept2" command to display the masked account number (except for the last four digits).

#### vperiodrept

**Description:** View the designated transaction log document.

> **Note:** This command has been replaced with vtransset when communicating with a Commander Site Controller.

**URL Syntax:**
```
https://{sapphire_IP}/cgi-bin/CGILink?cmd=vperiodrept&period={period}&filename={filename}&cookie={cookie}
```

**Alternate:**
```
https://{sapphire_IP}/cgi-bin/CGILink?cmd=vperiodrept&period={period}&reptnum={reptnum}&cookie={cookie}
```

**Usage:**
- `filename`: must be date.seq, e.g. 2004-03-29.001 or use value returned from vtlogpdlist
- `period`: [1,2]
- `reptnum`: [1 = current, 2 = most recently closed, 3 = next most recently closed, 4 = etc.]
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `transactions.xsd`
- Namespace: none
- Root element: `transactionSet`

#### vperiodreptz

**Description:** View the designated transaction log document. The returned document is in gzip format.

**URL Syntax:**
```
https://{sapphire_IP}/cgi-bin/CGILink?cmd=vperiodreptz&period={period}&filename={filename}&cookie={cookie}
```

#### vperiodrept2

**Description:** View the designated transaction log with credit card account numbers masked, except for what is permitted under PA-DSS.

**URL Syntax:**
```
https://{sapphire_IP}/cgi-bin/CGILink?cmd=vperiodrept2&period={period}&filename={filename}&cookie={cookie}
```

#### vtransset

**Description:** View the designated transaction log document from Commander Site Controller.

**URL Syntax:**
```
https://{commander_IP}/cgi-bin/CGILink?cmd=vtransset&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- XML Schema Document: `transset.xsd`
- Namespace: none
- Root element: `transSet`

#### vtranssetz

**Description:** View the designated transaction log document from Commander Site Controller. The returned document is in gzip format.

**URL Syntax:**
```
https://{commander_IP}/cgi-bin/CGILink?cmd=vtranssetz&period={period}&filename={filename}&cookie={cookie}
```

---

### Viewing Database Reports

> **Recommendation:** It is recommended that you use the filename parameter instead of reptnum.

#### vcashierrept

**Description:** View the cashier report for a given cashier period, register, and cashier.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vcashierrept&filename={filename}&cookie={cookie}&cashierNum={cashier number}&regNum={register number}
```

**Usage:**
- `filename`: Use value returned from vreportpdlist or must be date.seq (e.g. 2004-03-29.001)
- `cashierNum`: Cashier number
- `regNum`: Register used
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `periodTargs.xsd`
- Namespace: `urn:vfi-sapphire:pd.2002-05-21`
- Root element: `cashierPd`

#### vesafecashierrept

**Description:** View the cashier specific electronic safe report for a given cashier period, register, and cashier.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vesafecashierrept&filename={filename}&cookie={cookie}&cashierNum={cashier number}&regNum={register number}
```

**Locator:**
- XML Schema Document: `periodTargs.xsd`
- Namespace: `urn:vfi-sapphire:pd.2002-05-21`
- Root element: `eSafeCashierPd`

---

### Ruby Report Commands (vrubyrept)

All Ruby reports follow this general pattern:

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname={report_type}&period={period}&filename={filename}&cookie={cookie}
```

**Alternate:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname={report_type}&period={period}&reptnum={reptnum}&cookie={cookie}
```

**Common Parameters:**
- `period`: [1, 2, 3, 4]
- `reptnum`: [1 = current, 2 = most recently closed, 3 = next most recently closed, 4 = etc.]
- `cookie`: Credential valid for this session

**Locator (Common for all vrubyrept reports):**
- XML Schema Document: `periodTargs.xsd`
- Namespace: `urn:vfi-sapphire:pd.2002-05-21`

#### Available Report Types

| Report Type | reptname | Root Element | Description |
|-------------|----------|--------------|-------------|
| **Summary** | summary | summaryPd | Summary report for a given period and period type |
| **Department** | department | departmentPd | Department sales report |
| **Tax** | tax | taxPd | Tax report |
| **Hourly** | hourly | hourlyPd | Hourly sales report |
| **Network** | network | networkPd | Network report |
| **Deal** | deal | dealPd | Deal (mix-match and combo) report |
| **PLU** | plu | pluPd | PLU (price look-up code) sales report |
| **Category** | category | categoryPd | Category sales report |
| **Cash Acceptor** | cashAcc | cashAccPd | Cash acceptor report |
| **Car Wash** | carWash | carWashPd | Car wash report |
| **Proprietary Card** | propCard | propCardPd | Proprietary card report |
| **Proprietary Product** | propProd | propProdPd | Proprietary card network report by product code |
| **Money Order Device** | moneyOrderDev | moDevicePd | Money order (device totals) report |
| **Network Totals** | networkTotals | networkPd | Network totals report |
| **Car Wash Pay Point** | cwPaypoint | cwPaypointPd | Car wash pay point activity |
| **E-Safe EOD** | esafeeod | eSafeDayPd | Electronic safe end of day report |
| **E-Safe Content** | esafecontent | eSafeContentPd | Electronic safe content report |
| **E-Check** | eCheck | eCheckPd | Electronic check report |

#### Special Parameters for Specific Reports

**Tax Report:**
- Additional parameter: `filenameEnd={filename}` - Used to specify a period range to process the reports

**PLU Report:**
- Additional parameter: `reptDept={reptnum}` - Department number. Only PLUs belonging to the specified department will be in the report.
- `filenameEnd` parameter also available for period range

---

### Viewing Fuel Reports

#### vrubyrept/popDisc

**Description:** View the POP fuel discount report for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=popDisc&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `popDiscPd`

#### vrubyrept/dcrStat

**Description:** View the DCR statistics report for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=dcrStat&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `dcrstPd`

#### vrubyrept/fpHoseTest

**Description:** View the hose test by fueling position report for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=fpHoseTest&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `fptHosePd`

#### vrubyrept/fpHose

**Description:** View the fuel hose report for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=fpHose&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `fpHosePd`

#### vrubyrept/fpHoseRunning

**Description:** View the fuel hose running report.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=fpHoseRunning&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `fpHoseRunningPd`

#### vrubyrept/prPriceLvl

**Description:** View the fuel activity by product/price level for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=prPriceLvl&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `prPriceLvlPd`

#### vrubyrept/slPriceLvl

**Description:** View the fuel activity by service-level/price-level for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=slPriceLvl&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `slPriceLvlPd`

#### vrubyrept/tierProduct

**Description:** View the fuel activity by tier/product for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=tierProduct&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `tierProductPd`

#### vrubyrept/autoCollect

**Description:** View the fuel auto-collect report for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=autoCollect&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `autoCollectPd`

#### vrubyrept/tank

**Description:** View the fuel tank report for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=tank&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `tankPd`

#### vrubyrept/tankMonitor

**Description:** View the fuel tank monitor report (device totals) for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=tankMonitor&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `tankMonitorPd`

#### vrubyrept/tankRec

**Description:** View the tank reconciliation report for a given period and period type. This report reconciles between fuel tank report and tank monitor report.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrubyrept&reptname=tankRec&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- Root element: `tankRecPd`

#### vfueltotals

**Description:** View fuel dispenser (device totals) report for a given period and period type.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vfueltotals&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- XML Schema Document: `vsmsFuel.xsd`
- Namespace: `urn:vfi-sapphire:fuel.2001-10-01`
- Root element: `fuelTotals`

#### vfueltotalsz

**Description:** View fuel dispenser (device totals) report for a given period and period type. The returned document is in gzip format.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vfueltotalsz&period={period}&filename={filename}&cookie={cookie}
```

**Locator:**
- XML Schema Document: `vsmsFuel.xsd`
- Namespace: `urn:vfi-sapphire:fuel.2001-10-01`
- Root element: `fuelTotals`

---

### Viewing Car Wash Pay Point Reports

#### vcwpaypointpdrept

**Description:** View the car wash pay point reconciliation data.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vcwpaypointpdrept&filename={filename}&cookie={cookie}
```

**Usage:**
- `filename`: Use value returned from vcwpaypointpdlist or must be date.seq (e.g. 2004-03-29.001)
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `periodTargs.xsd`
- Namespace: `urn:vfi-sapphire:pd.2002-05-21`
- Root element: `cwPaypointReconciliation`

---

## 3. Maintenance Functions

> **Note:** GET command names begin with a 'v'; POST command names begin with a 'u'.

### Commander-Specific Commands

#### umanagedcfg

**Description:** Allows for the "staging of" PLUs/Items and the site decides when to commit the changes based on a separate POS action.

**URL Syntax (Verifone):**
```
https://{commander_IP}/cgi-bin/CGIUplink?cmd=umanagedcfg&subcmd=plu&cookie={cookie}
```

**URL Syntax (NAXML):**
```
https://{commander_IP}/cgi-bin/NAXML?cmd=umanagedcfg&subcmd=Item&cookie={cookie}
```

**Usage:**
- `subcmd`: Must be 'plu' or 'Item'
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `PLUs.xsd`
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `PLUs`

> **Note:** When the first request of staged changes is posted to the Commander, a message is displayed on the POS alerting the site that changes are pending.

#### vmanagedcfgstatus

**Description:** Returns a list of pending changes that will take effect the next time the site decides to accept the changes on the POS.

**URL Syntax:**
```
https://{commander_IP}/cgi-bin/CGILink?cmd=vmanagedcfgstatus&cookie={cookie}
```

**Locator:**
- XML Schema Document: `vsmsConfigData.xsd`
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `managedUpdateInfo`

---

### Configuration Commands (View/Update Pairs)

Most configuration commands come in pairs - a view command (v*) and an update command (u*).

#### Screen Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vscreencfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uscreencfg&cookie={cookie}
```

**Locator:**
- XML Schema Document: `screencfg.xsd`
- Namespace: no namespace
- Root element: `screencfg`

#### In-House Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vinhousecfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uinhousecfg&cookie={cookie}
```

**Description:** Contains account numbers and names for In House accounts.

**Locator:**
- XML Schema Document: `houseAcctConfig.xsd`
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `houseAcctConfig`

#### User Administration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vuseradmin&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uuseradmin&cookie={cookie}
```

**Description:** User document, including users and user roles and permissions.

**Locator:**
- XML Schema Document: `vsmsConfigData.xsd`
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `userConfig`

#### Sapphire Properties

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vsapphireprop&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=usapphireprop&cookie={cookie}
```

**Description:** Site Controller properties document (for technical personnel only).

**Locator:**
- XML Schema Document: none
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `sapphireProperties`

---

### Commander Fuel Configuration

#### vfuelcfg

**View:**
```
https://{commander_IP}/cgi-bin/CGILink?cmd=vfuelcfg&cookie={cookie}
```

**Update:**
```
https://{commander_IP}/cgi-bin/CGIUplink?cmd=ufuelcfg&cookie={cookie}
```

**Description:** Fuel configuration document on Commander, including service modes, tanks, blends, fueling positions, hose assignments and grade pricing.

**Locator:**
- XML Schema Document: `pscFuelConfig.xsd`
- Namespace: `urn:vfi-psc:fuel.2013-02-08`
- Root element: `fuelConfig`

#### vpscdcrcfg

**View:**
```
https://{commander_IP}/cgi-bin/CGILink?cmd=vpscdcrcfg&cookie={cookie}
```

**Update:**
```
https://{commander_IP}/cgi-bin/CGIUplink?cmd=upscdcrcfg&cookie={cookie}
```

**Description:** DCR configuration document on Commander, which shows the headers, messages, and trailers for DCRs.

**Locator:**
- XML Schema Document: `pscDCRConfig.xsd`
- Namespace: `urn:vfi-psc:dcr.2012-04-10`
- Root element: `dcrConfig`

---

### Deal Configuration

#### vexpandeddealcfg

**View:**
```
https://{sapphire_IP}/cgi-bin/CGILink?cmd=vexpandeddealcfg&cookie={cookie}
```

**Update:**
```
https://{sapphire_IP}/cgi-bin/CGIUplink?cmd=uexpandeddealcfg&cookie={cookie}
```

**Description:** View/update the interim deal configuration.

**Locator:**
- XML Schema Document: `expandedDealCfg.xsd`
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `expandedDealConfig`

---

### VIPER/FEP Configuration

#### vfepdetails

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vfepdetails&cookie={cookie}
```

**Description:** View basic details about the available FEPs.

**Locator:**
- XML Schema Document: `viperConfigImpl.xsd`
- Namespace: `core.viper.verifone.com.2011-11-08`
- Root element: `fepDetails`

#### vvipercfg

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vvipercfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uvipercfg&cookie={cookie}
```

**Description:** View/update PMC's Site level Configuration.

**Locator:**
- XML Schema Document: `viperConfigImpl.xsd`
- Namespace: `core.viper.verifone.com.2011-11-08`
- Root element: `viperConfig`

#### vfepcfg

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vfepcfg&fep={fepName}&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ufepcfg&fep={fepName}&cookie={cookie}
```

**Description:** View/update FEP's configuration. The command needs to be qualified with the fep name for which configuration is requested (see vfepdetails).

**Usage:**
- `fepName`: Use @fep from vfepdetails

**Locator:**
- XML Schema Document: `viperConfigImpl.xsd`
- Namespace: `core.viper.verifone.com.2011-11-08`
- Root element: `fepConfig`

#### vfepcardcfg

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vfepcardcfg&fep={fepName}&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ufepcardcfg&fep={fepName}&cookie={cookie}
```

**Description:** View/update FEP's card table configuration. This command may not be supported by all the FEPs.

**Locator:**
- XML Schema Document: `viperConfigImpl.xsd`
- Namespace: `core.viper.verifone.com.2011-11-08`
- Root element: `fepCardTableConfig`

#### vfepcardtypecfg

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vfepcardtypecfg&fep={fepName}&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ufepcardtypecfg&fep={fepName}&cookie={cookie}
```

**Description:** View/update FEP's card type level configuration (the configuration applies to multiple card table entries which matches a particular type). This command may not be supported by all the FEPs.

**Locator:**
- XML Schema Document: `viperConfigImpl.xsd`
- Namespace: `core.viper.verifone.com.2011-11-08`
- Root element: `fepCardTypeConfig`

---

### Additional Configuration Commands

#### Deal Configuration (vdealcfg)

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vdealcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=udealcfg&cookie={cookie}
```

**Description:** Deal (mix-match and combo) configuration document.

**Locator:**
- Root element: `dealConfig`

#### Register Configuration (vregistercfg)

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vregistercfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uregistercfg&cookie={cookie}
```

**Description:** Register parameter configuration: banner, logo/slogan, check frank line, menu keys, keyboard, and softkeys.

**Locator:**
- Root element: `registerConfig`

#### Payment Configuration (vpaymentcfg)

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vpaymentcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=upaymentcfg&cookie={cookie}
```

**Description:** Method of payment (MOP), fee, currency, tax rate, and break points.

**Locator:**
- Root element: `paymentConfig`

#### POS Configuration (vposcfg)

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vposcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uposcfg&cookie={cookie}
```

**Description:** Department, category, and product code.

**Locator:**
- Root element: `posConfig`

#### Fuel Site Configuration (Sapphire)

**View:**
```
https://{sapphire_IP}/cgi-bin/CGILink?cmd=vfuelsite&cookie={cookie}
```

**Update:**
```
https://{sapphire_IP}/cgi-bin/CGIUplink?cmd=ufuelsite&cookie={cookie}
```

**Description:** Fuel site configuration including hose assignments, service modes, tanks, blends, products, and fueling positions.

**Locator:**
- XML Schema Document: `vsmsFuel.xsd`
- Namespace: `urn:vfi-sapphire:fuel.2001-10-01`
- Root element: `fuelSite`

#### Restrictions Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrestrictionscfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=urestrictionscfg&cookie={cookie}
```

**Description:** Age, blue-law (including time-of-day), and PLU Promo restrictions.

**Locator:**
- Root element: `restrictionsConfig`

#### POS Security

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vpossecurity&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=upossecurity&cookie={cookie}
```

**Description:** Security and employee control. Additional validation required for update.

**Locator:**
- Root element: `posSecurity`

#### DCR Configuration (Sapphire)

**View:**
```
https://{sapphire_IP}/cgi-bin/CGILink?cmd=vdcrcfg&cookie={cookie}
```

**Update:**
```
https://{sapphire_IP}/cgi-bin/CGIUplink?cmd=udcrcfg&cookie={cookie}
```

**Description:** DCR configuration: headers, messages, and trailers.

**Locator:**
- Root element: `dcrConfig`

#### Referential Integrity

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vrefinteg&cookie={cookie}
```

**Description:** Referential integrity document for validation of dataset configurations at the client end. Read-only, to be used as a reference for filling in other update documents.

**Locator:**
- XML Schema Document: `vsmsRefInteg.xsd`
- Root element: `referentialIntegrity`

#### Sales Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vsalescfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=usalescfg&cookie={cookie}
```

**Description:** Sales operational parameters configuration.

**Locator:**
- Root element: `salesConfig`

#### POP Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vpopcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=upopcfg&cookie={cookie}
```

**Description:** POP fuel discount configuration.

**Locator:**
- Root element: `popConfig`

#### Tank Level Sensor

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vtlssite&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=utlssite&cookie={cookie}
```

**Description:** Tank level sensor configuration.

**Locator:**
- Root element: `tlsSiteInfo`

#### Car Wash Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vcarwashcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ucarwashcfg&cookie={cookie}
```

**Description:** Car wash configuration.

**Locator:**
- Root element: `carWashConfig`

#### Cash Acceptor Site

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vcashaccsite&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ucashaccsite&cookie={cookie}
```

**Description:** Cash acceptor configuration.

**Locator:**
- Root element: `cashAccSiteInfo`

#### Age Validation Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vagevalidationcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uagevalidationcfg&cookie={cookie}
```

**Description:** Age validation (ID check) configuration.

**Locator:**
- Root element: `ageValidationConfig`

#### Banner Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vbannercfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ubannercfg&cookie={cookie}
```

**Description:** Banner configuration used to program customer display banners.

**Locator:**
- Root element: `bannerConfig`

#### Blue Law Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vbluelawcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ubluelawcfg&cookie={cookie}
```

**Description:** Blue law configuration.

**Locator:**
- Root element: `blueLawConfig`

#### DCR Receipt Configuration

**Header:**

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vdcrheadercfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=udcrheadercfg&cookie={cookie}
```

**Locator:** Root element: `dcrHeaderConfig`

**Message:**

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vdcrmessagecfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=udcrmessagecfg&cookie={cookie}
```

**Locator:** Root element: `dcrMessageConfig`

**Trailer:**

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vdcrtrailercfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=udcrtrailercfg&cookie={cookie}
```

**Locator:** Root element: `dcrTrailerConfig`

> **Note:** These commands only affect printing at the DCR, as opposed to udcrcfg which configures DCRs over the site.

#### Fee Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vfeecfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ufeecfg&cookie={cookie}
```

**Locator:**
- Root element: `feeConfig`

#### Logo Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vlogocfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ulogocfg&cookie={cookie}
```

**Locator:**
- Root element: `logoConfig`

#### Slogan Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vslogancfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uslogancfg&cookie={cookie}
```

**Locator:**
- Root element: `sloganConfig`

#### Tax Rate Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vtaxratecfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=utaxratecfg&cookie={cookie}
```

**Locator:**
- Root element: `taxRateConfig`

#### Date and Time

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vdatetime&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=udatetime&cookie={cookie}
```

**Description:** Current system date and time configuration.

**Locator:**
- Root element: `sysDateTime`

#### Period Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vperiodcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uperiodcfg&cookie={cookie}
```

**Description:** Period names and period close options.

**Locator:**
- Root element: `periodConfig`

#### Maintenance Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vmaintcfg&cookie={cookie}
```

**View with specific dataset:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vmaintcfg&cookie={cookie}&dataset={dataset_name}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=umaintcfg&cookie={cookie}
```

**Description:** Obtain/update information about the Site Controller system.

**Available Datasets:**
- `versioninfo`
- `ioconfig`
- `totalizers`
- `fprht`
- `features`
- `registration`
- `telephone`
- `postal`

**Locator:**
- XML Schema Document: `vsmsMaintenance.xsd`
- Namespace: `urn:vfi-sapphire:np.gpmaint.2004-08-03`
- Root element: `maintenance`

#### PLU Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGIPLULink?cmd=vPLUs&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIPLULink?cmd=uPLUs&cookie={cookie}
```

**Description:** View/update PLU configuration document on Site Controller.

**Locator:**
- XML Schema Document: `PLUs.xsd`
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element (view): `PLUSelect`
- Root element (update): `PLUs`

#### Change Password

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=changepasswd&cookie={cookie}
```

**Description:** Change the password for the user associated with a credential.

**Locator:**
- Root element: `passwdConfig`

#### Electronic Safe Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vesafecfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uesafecfg&cookie={cookie}
```

**Locator:**
- Root element: `eSafeConfig`

#### Car Wash Pay Point Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vcwpaypointcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ucwpaypointcfg&cookie={cookie}
```

**Locator:**
- Root element: `cwPaypointConfig`

#### Loyalty Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vloyaltycfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uloyaltycfg&cookie={cookie}
```

**Locator:**
- Root element: `loyaltyConfig`

#### Fuel Price Display Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vFPDcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=uFPDcfg&cookie={cookie}
```

**Description:** Fuel Price Sign configuration.

**Locator:**
- XML Schema Document: `vsmsFuelPriceDisplay.xsd`
- Namespace: `urn:vfi-sapphire:fuelPriceDisplay.2005-03-15`
- Root element: `fuelPriceDisplay`

#### Fuel Prices

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vfuelprices&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=ufuelprices&cookie={cookie}
```

**Locator:**
- XML Schema Document: `vsmsFuel.xsd`
- Namespace: `urn:vfi-sapphire:fuel.2001-10-01`
- Root element: `fuelPrices`

#### Signature Capture Configuration

**View:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vsigcapcfg&cookie={cookie}
```

**Update:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=usigcapcfg&cookie={cookie}
```

**Locator:**
- Root element: `sigCaptureConfig`

---

### Initialization Commands

#### cfuelinit

**Description:** To fully initialize/download all configuration data and prices to the fuel dispensers.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=cfuelinit&cookie={cookie}
```

**Locator:**
- XML Schema Document: `RPC.xsd`
- Root element: `Response`

#### cfuelprices

**Description:** To initialize/download fuel prices to the dispensers.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=cfuelprices&cookie={cookie}
```

**Locator:**
- XML Schema Document: `RPC.xsd`
- Root element: `Response`

#### cdcrinit

**Description:** To initialize/download a specific or all Dispenser Card Reader(s).

**URL Syntax (specific dispenser):**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=cdcrinit&fuelingposition={fuelpos}&cookie={cookie}
```

**URL Syntax (all dispensers):**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=cdcrinit&cookie={cookie}
```

**Usage:**
- `fuelpos`: A fueling position to initialize. To download all, omit the fueling position completely.

**Locator:**
- XML Schema Document: `RPC.xsd`
- Root element: `Response`

#### cFPDinit

**Description:** To fully initialize/download all configuration data and prices to the fuel price sign.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=cFPDinit&cookie={cookie}
```

**Locator:**
- XML Schema Document: `RPC.xsd`
- Root element: `Response`

---

## 4. Event Notification

### Overview

Event notification is a feature of Site Controller that enables the ability to have the Site Controller POST an Event Notification XML to a registered "listener" via HTTP.

> **Note:** HTTPS is not supported at this time.

The configuration of events requires:
1. A user with `veventset`, `veventunset`, and `repeatEvent` function(s)
2. The session "cookie" to perform the setup
3. A registered listener (web server that can accept a POST of XML)

**Locator:**
- XML Schema Document: `vsmsEvents.xsd`
- Namespace: `urn:vfi-sapphire:event.2004-03-22`
- Root element: `fault`, `genericEvent`, `appStartEvent`, `rebootEvent`, `periodCloseEvent`, `csrAuditEvent`, `fuelInitEvent`

### Set Event

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=veventset&URL={URL}&username={username}&alias={alias}&eventType={eventType}&cookie={cookie}
```

**Usage:**
- `URL`: Fully qualified URL including the port number and ASP or CGI to process the event  
  Example: `http://10.10.10.10:8080/cgi-bin/processSapphireEvent`
- `username`: An existing user on the Site Controller which has sufficient privileges to complete the tasks by the event listener
- `alias`: A unique name (shorthand) per eventType to tie the username and URL together  
  **Note:** Although spaces are permitted at this time, it is recommended NOT to use them.
- `eventType`: The allowed values are: `APP_START`, `FUEL_INIT`, `FUNDS_AUDIT`, or `PERIOD_CLOSE`
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `RPC.xsd`
- Root element: `Response`

### Remove Event

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=veventunset&alias={alias}&eventType={eventType}&cookie={cookie}
```

**Usage:**
- `alias`: A unique name (shorthand) per eventType
- `eventType`: The allowed values are: `APP_START`, `FUEL_INIT`, `FUNDS_AUDIT`, or `PERIOD_CLOSE`
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `RPC.xsd`
- Root element: `Response`

### Repeat Last Event

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=repeatEvent&eventType={eventType}&alias={alias}&period={period}&cookie={cookie}
```

**Usage:**
- `alias`: A unique name (shorthand) per eventType
- `eventType`: The allowed values are: `APP_START`, `FUEL_INIT`, `FUNDS_AUDIT`, or `PERIOD_CLOSE`
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `RPC.xsd`
- Root element: `Response`

---

## 5. Deprecated Commands

The following commands should no longer be used, but they may be supported or available in some versions of Site Controller.

### vfuelposstat

**Description:** View the current status of all fueling positions.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vfuelposstat&cookie={cookie}
```

### vnetcfg

**Description:** View the network configuration document.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vnetcfg&cookie={cookie}
```

### unetcfg

**Description:** Update the network configuration document.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGIUplink?cmd=unetcfg&cookie={cookie}
```

### vPLUUpdateStatus

**Description:** View the status of the PLU transfer to and from the Ruby controller.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGIPLULink?cmd=vPLUUpdateStatus&cookie={cookie}
```

### vPLUCacheList

**Description:** View PLU cache list.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGIPLULink?cmd=vPLUCacheList&cookie={cookie}
```

### uPLUCacheList

**Description:** Update PLU cache list.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGIPLULink?cmd=uPLUCacheList&cookie={cookie}
```

### getPLUsFromGempro

**Description:** Initiate a transfer of PLUs from the Ruby controller to the Site Controller database.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=getPLUsFromGempro&cookie={cookie}
```

### sendPLUsToGempro

**Description:** Initiate a transfer of PLUs already in the Site Controller database to the Ruby or Topaz.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=sendPLUsToGempro&cookie={cookie}
```

### vpayrollpdlist

**Description:** Get a list of all the payroll report periods available.

**URL Syntax:**
```
https://{site-controller_IP}/cgi-bin/CGILink?cmd=vpayrollpdlist&cookie={cookie}
```

**Locator:**
- Namespace: `urn:vfi-sapphire:np.domain.2001-07-01`
- Root element: `periodList`

---

## 6. NAXML APIs

### Overview

Processing Site Controller information into and out of the NAXML transfer syntax requires coordination of a variety of processing resources.

**Implementation Philosophy:**
1. Let every NAXML request be launched using a consistently formulated URL
2. For simple cases, let the Site Controller do a straightforward XSLT transform
3. For complex cases, write Java "visitors" to create NAXML directly from Java persistent objects
4. For cases where a NAXML report can/should be created from the transaction log, provide an alternate processor

**Restrictions:**
- `//RecordAction/@type = (addchange | delete)` - No other values honored
- `//TableAction/@type = (update | initialize)` - No other values honored

### Site Controller Commands

**Single processing entry point:**
```
https://{site-controller_IP}/cgi-bin/NAXML
```

**Example:**
```
https://{site-controller_IP}/cgi-bin/NAXML?cmd=vMaintenance&dataset=ItemList&cookie={cookie}
```

### NAXML POS Journal

#### vposjournal

**Description:** The NAXML POSJournal format of vtransset from the Commander. Can be either a POST or a GET.

**URL Syntax:**
```
https://{commander_IP}/cgi-bin/NAXML?cmd=vposjournal&period={period}&filename={filename}&cookie={cookie}
```

**Alternate:**
```
https://{commander_IP}/cgi-bin/NAXML?cmd=vposjournal&period={period}&reptnum={reptnum}&cookie={cookie}
```

**Usage:**
- `filename`: Must be date.seq (e.g. 2004-03-29.001) or use value returned from vtlogpdlist
- `period`: [1,2]
- `reptnum`: [1 = current, 2 = most recently closed, 3 = next most recently closed, 4 = etc.]
- `cookie`: Credential valid for this session

**Locator:**
- XML Schema Document: `naxmlPrefs.xsd`
- Namespace: no namespace
- Root element: `NAXMLPrefs`

> **Note:** In the case of a GET, the default NAXMLPrefs rules are applied, otherwise the posted NAXMLPrefs override the defaults.

### Movement

The Movement API is symmetrical. Each document must be requested through a specific URL.

**Format:**
```
https://{site-controller_IP}/cgi-bin/NAXML?cmd=vMovement&dataset={DATASET}&cookie={cookie}
```

**Available Datasets:**

| Dataset | Description | Report Details |
|---------|-------------|----------------|
| **FuelGrade** | Fuel Grade Report | Totals broken down by Products then Tender/Service-Level, Fueling position, and Resettable totals |
| **FuelProduct** | Fuel Product Report | Non-resettable fuel totals (Dispenser Report) |
| **ItemSales** | Item Sales Report | PLU Report |
| **MerchandiseCode** | Merchandise Code Report | Department Report |
| **MiscellaneousSummary** | Miscellaneous Summary Report | KPIs Similar to Summary Report |
| **TankProduct** | Tank Product Report | TLS Report |
| **TaxLevel** | Tax Level Report | Tax Report |

**Examples:**

Using filename:
```
https://{site-controller_IP}/cgi-bin/NAXML?cmd=vMovement&dataset=FuelGrade&period={period}&filename={filename}&cookie={cookie}
```

Using report number:
```
https://{site-controller_IP}/cgi-bin/NAXML?cmd=vMovement&dataset=FuelGrade&period={period}&reptnum={reptnum}&cookie={cookie}
```

### Maintenance

The API is asymmetrical:
- Datasets are always **retrieved** using a specific URL
- Configuration documents may be **submitted** using:
  - A single general purpose URL
  - A specific URL

**View Format:**
```
https://{site-controller_IP}/cgi-bin/NAXML?cmd=vMaintenance&dataset={DATASET}&cookie={cookie}
```

**Update Format:**
```
https://{site-controller_IP}/cgi-bin/NAXML?cmd=uMaintenance&dataset={DATASET}&cookie={cookie}
```

**Available Datasets:**

| Dataset | Description | View/Update |
|---------|-------------|-------------|
| **All** | Process a NAXMLPBIMaintenance document, allowing any dataset to change | Update only |
| **FuelGrade** | Review or update fuel grades in use at the site | Both |
| **FuelPosition** | Review or update dispensers, payment modes, hoses at each position | Both |
| **FuelProduct** | Review or update fuel products (not blended) available at the site | Both |
| **TankProduct** | Review or update which products are in which tanks | Both |
| **MerchandiseCode** | Review or update departments | Both |
| **ItemList** | Review or update lists of items with a common identifier (used in Mix/Match and Combo) | Both |
| **Item** | Review or update PLUs | Both |
| **MixMatch** | Review or update mix-match entries | Both |
| **Combo** | Review or update combo entries | Both |
| **TaxLevel** | Review or update tax percentages or pointers to internal tables | Both |
| **TaxIncludes** | Review or update different kinds of included tax | Both |
| **TaxStrategy** | Review or update patterns of TaxLevel and TaxIncludes items | Both |

**Examples:**

View FuelGrade:
```
https://{site-controller_IP}/cgi-bin/NAXML?cmd=vMaintenance&dataset=FuelGrade&cookie={cookie}
```

Update FuelGrade:
```
https://{site-controller_IP}/cgi-bin/NAXML?cmd=uMaintenance&dataset=FuelGrade&cookie={cookie}
```

Update All (general purpose):
```
https://{site-controller_IP}/cgi-bin/NAXML?cmd=uMaintenance&dataset=All&cookie={cookie}
```

> **Note:** When using the "All" dataset, the user credential must allow the user to change all datasets, regardless of the content of the document.

### PC Commands

Commands passed through to the PC from the Site Controller have exactly the same form, except for the HPV-20 address prefix.

**Example:**
```
https://hpv-20:8080/NAXML.ASP?cmd=vMaintenance&dataset=MerchandiseCode&cookie={cookie}
```

> **Note:** The HPV-20 IIS Server listens on port 8080. NAXML is an Active Server Page (ASP).

### Errors and Success Status Reporting

Errors and success status must be via a returned XML document conforming to: `vfischema/RPC.xsd`

**Error Document Returned In These Cases:**
- The request to view or post a dataset points to an invalid dataset
- The request to post a dataset contains invalid data leading to unrecoverable errors
- The request to view a given report points to an invalid report
- The request to view a given report has parameters that indicate a report that is not available (e.g., unavailable date)

---

## Common Locator Information

Most commands use the following common XML schema information:

**Namespace:** `urn:vfi-sapphire:np.domain.2001-07-01`

**XML Schema Documents:**
- `vsmsConfigData.xsd` - Configuration data
- `credential.xsd` - Credentials
- `RPC.xsd` - RPC responses
- `transactions.xsd` - Transaction logs
- `periodTargs.xsd` - Period reports
- `vsmsFuel.xsd` - Fuel data
- `vsmsRefInteg.xsd` - Referential integrity
- `vsmsMaintenance.xsd` - Maintenance
- `PLUs.xsd` - PLU data
- `vsmsEvents.xsd` - Events

---

## Copyright Notice

© 2016 Verifone, Inc. All rights reserved.

Verifone®, Ruby SuperSystem®, and Secure PumpPAY® are registered trademarks of Verifone, Inc.  
Ruby Card™, iOrder™, and Commander Site Controller™ are trademarks of Verifone.

---

**Document Information:**
- **Version:** 2.00.01
- **Date:** April 22, 2016
- **Company:** Verifone, Inc.
- **Address:** 88 West Plumeria Drive, San Jose, CA 95134
- **Telephone:** 408-232-7800
- **Website:** http://www.verifone.com
