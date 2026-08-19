// Mirrors ape-platform-charts/crossplane-compositions-dns/templates/compositions/record.yaml's
// $resolvedAliasZoneId derivation EXACTLY (same regions, same zone IDs, same fallback-to-empty
// behavior) so this preview never shows a different answer than what the platform will actually
// write. If you change the composition's table, update this one too.

export const GLOBAL_SERVICE_TYPES = ['CloudFront', 'GlobalAccelerator'] as const;
export const REGIONAL_ALB_NLB_TYPES = ['ALB', 'NLB'] as const;
export const REGIONAL_S3_APIGW_TYPES = ['S3Website', 'APIGateway'] as const;
export const REGIONAL_ELASTICBEANSTALK_TYPES = ['ElasticBeanstalk'] as const;

const GLOBAL_ZONE_IDS: Record<string, string> = {
  CloudFront: 'Z2FDTNDATAQYW2',
  GlobalAccelerator: 'Z2BJ6XQ5FK7U4H',
};

const ALB_ZONE_IDS: Record<string, string> = {
  'us-east-1': 'Z35SXDOTRQ7X7K',
  'us-east-2': 'Z3AADJGX6KTTL2',
  'us-west-1': 'Z368ELLRRE2KJ0',
  'us-west-2': 'Z1H1FL5HABSF5',
  'ca-central-1': 'ZQSVJUPU6J1EY',
  'ca-west-1': 'Z06473681N0SF6OS049SD',
  'af-south-1': 'Z268VQBMOI5EKX',
  'ap-east-1': 'Z3DQVH9N71FHZ0',
  'ap-east-2': 'Z02789141MW7T1WBU19PO',
  'ap-south-1': 'ZP97RAFLXTNZK',
  'ap-south-2': 'Z0173938T07WNTVAEPZN',
  'ap-southeast-1': 'Z1LMS91P8CMLE5',
  'ap-southeast-2': 'Z1GM3OXH4ZPM65',
  'ap-southeast-3': 'Z08888821HLRG5A9ZRTER',
  'ap-southeast-4': 'Z09517862IB2WZLPXG76F',
  'ap-southeast-5': 'Z06010284QMVVW7WO5J',
  'ap-southeast-6': 'Z023301818UFJ50CIO0MV',
  'ap-southeast-7': 'Z0390008CMBRTHFGWBCB',
  'ap-northeast-1': 'Z14GRHDCWA56QT',
  'ap-northeast-2': 'ZWKZPGTI48KDX',
  'ap-northeast-3': 'Z5LXEXXYW11ES',
  'eu-west-1': 'Z32O12XQLNTSW2',
  'eu-west-2': 'ZHURV8PSTC4K8',
  'eu-west-3': 'Z3Q77PNBQS71R4',
  'eu-central-1': 'Z215JYRZR1TBD5',
  'eu-central-2': 'Z06391101F2ZOEP8P5EB3',
  'eu-north-1': 'Z23TAZ6LKFMNIO',
  'eu-south-1': 'Z3ULH7SSC9OV64',
  'eu-south-2': 'Z0956581394HF5D5LXGAP',
  'il-central-1': 'Z09170902867EHPV2DABU',
  'mx-central-1': 'Z023552324OKD1BB28BH5',
  'me-central-1': 'Z08230872XQRWHG2XF6I',
  'me-south-1': 'ZS929ML54UICD',
  'sa-east-1': 'Z2P70J7HTTTPLU',
  'cn-north-1': 'Z1GDH35T77C1KE',
  'cn-northwest-1': 'ZM7IZAIOVVDZF',
  'us-gov-east-1': 'Z166TLBEWOO7G0',
  'us-gov-west-1': 'Z33AYJ8TM3BH4J',
};

const NLB_ZONE_IDS: Record<string, string> = {
  'us-east-1': 'Z26RNL4JYFTOTI',
  'us-east-2': 'ZLMOA37VPKANP',
  'us-west-1': 'Z24FKFUX50B4VW',
  'us-west-2': 'Z18D5FSROUN65G',
  'ca-central-1': 'Z2EPGBW3API2WT',
  'ca-west-1': 'Z02754302KBB00W2LKWZ9',
  'af-south-1': 'Z203XCE67M25HM',
  'ap-east-1': 'Z12Y7K3UBGUAD1',
  'ap-east-2': 'Z09176273OC2HWIAUNYW',
  'ap-south-1': 'ZVDDRBQ08TROA',
  'ap-south-2': 'Z0711778386UTO08407HT',
  'ap-southeast-1': 'ZKVM4W9LS7TM',
  'ap-southeast-2': 'ZCT6FZBF4DROD',
  'ap-southeast-3': 'Z01971771FYVNCOVWJU1G',
  'ap-southeast-4': 'Z01156963G8MIIL7X90IV',
  'ap-southeast-5': 'Z026317210H9ACVTRO6FB',
  'ap-southeast-6': 'Z01392953RKV2Q3RBP0KU',
  'ap-southeast-7': 'Z054363131YWATEMWRG5L',
  'ap-northeast-1': 'Z31USIVHYNEOWT',
  'ap-northeast-2': 'ZIBE1TIR4HY56',
  'ap-northeast-3': 'Z1GWIQ4HH19I5X',
  'eu-west-1': 'Z2IFOLAFXWLO4F',
  'eu-west-2': 'ZD4D7Y8KGAS4G',
  'eu-west-3': 'Z1CMS0P5QUZ6D5',
  'eu-central-1': 'Z3F0SRJ5LGBH90',
  'eu-central-2': 'Z02239872DOALSIDCX66S',
  'eu-north-1': 'Z1UDT6IFJ4EJM',
  'eu-south-1': 'Z23146JA1KNAFP',
  'eu-south-2': 'Z1011216NVTVYADP1SSV',
  'il-central-1': 'Z0313266YDI6ZRHTGQY4',
  'mx-central-1': 'Z02031231H3ID6HYJ9A7U',
  'me-central-1': 'Z00282643NTTLPANJJG2P',
  'me-south-1': 'Z3QSRYVP46NYYV',
  'sa-east-1': 'ZTK26PT1VY4CU',
  'cn-north-1': 'Z3QFB96KMJ7ED6',
  'cn-northwest-1': 'ZQEIKTCZ8352D',
  'us-gov-east-1': 'Z1ZSMQQ6Q24QQ8',
  'us-gov-west-1': 'ZMG1MZ2THAWF1',
};

const S3WEBSITE_ZONE_IDS: Record<string, string> = {
  'us-east-1': 'Z3AQBSTGFYJSTF',
  'us-east-2': 'Z2O1EMRO9K5GLX',
  'us-west-1': 'Z2F56UZL2M1ACD',
  'us-west-2': 'Z3BJ6K6RIION7M',
  'ca-central-1': 'Z1QDHH18159H29',
  'ca-west-1': 'Z03565811Z33SLEZTHOUL',
  'af-south-1': 'Z2OSFR5PIJ8TYW',
  'ap-east-1': 'ZNB98KWMFR0R6',
  'ap-east-2': 'Z064739330DAH7WJVOO93',
  'ap-south-1': 'Z11RGJOFQNVJUP',
  'ap-south-2': 'Z02976202B4EZMXIPMXF7',
  'ap-southeast-1': 'Z3O0J2DXBE1FTB',
  'ap-southeast-2': 'Z1WCIGYICN2BYD',
  'ap-southeast-3': 'Z01846753K324LI26A3VV',
  'ap-southeast-4': 'Z0312387243XT5FE14WFO',
  'ap-southeast-5': 'Z08660063OXLMA7F1FJHU',
  'ap-southeast-6': 'Z05686083R66JX5C163TC',
  'ap-southeast-7': 'Z0031014GXUMRZG6I14G',
  'ap-northeast-1': 'Z2M4EHUR26P7ZW',
  'ap-northeast-2': 'Z3W03O7B5YMIYP',
  'ap-northeast-3': 'Z2YQB5RD63NC85',
  'eu-west-1': 'Z1BKCTXD74EZPE',
  'eu-west-2': 'Z3GKZC51ZF0DB4',
  'eu-west-3': 'Z3R1K369G5AVDG',
  'eu-central-1': 'Z21DNDUVLTQW6Q',
  'eu-central-2': 'Z030506016YDQGETNASS',
  'eu-north-1': 'Z3BAZG2TWCNX0D',
  'eu-south-1': 'Z2OPA49AB41N7K',
  'eu-south-2': 'Z0081959F7139GRJC19J',
  'il-central-1': 'Z09640613K4A3MN55U7GU',
  'mx-central-1': 'Z057606446ZNVQJJ8WOP',
  'me-central-1': 'Z06143092I8HRXZRUZROF',
  'me-south-1': 'Z1MPMWCPA7YB62',
  'sa-east-1': 'Z7KQH4QJS55SO',
  'us-gov-east-1': 'Z2NIFVYYW2VKV1',
  'us-gov-west-1': 'Z31GFT0UA1I2HV',
};

const APIGATEWAY_ZONE_IDS: Record<string, string> = {
  'us-east-1': 'Z1UJRXOUMOOFQ8',
  'us-east-2': 'ZOJJZC49E0EPZ',
  'us-west-1': 'Z2MUQ32089INYE',
  'us-west-2': 'Z2OJLYMUO9EFXC',
  'ca-central-1': 'Z19DQILCV0OWEC',
  'ca-west-1': 'Z04745493436AWVTG1OQY',
  'af-south-1': 'Z2DHW2332DAMTN',
  'ap-east-1': 'Z3FD1VL90ND7K5',
  'ap-east-2': 'Z02909591O7FG9Q56HWB1',
  'ap-south-1': 'Z3VO1THU9YC4UR',
  'ap-south-2': 'Z0853509Q1135NJ66RUH',
  'ap-southeast-1': 'ZL327KTPIQFUL',
  'ap-southeast-2': 'Z2RPCDW04V8134',
  'ap-southeast-3': 'Z10132843TYUYSLUG4HA3',
  'ap-southeast-4': 'Z092189423Y7RJK61311D',
  'ap-southeast-5': 'Z0314042F0KBUTZ3X5HF',
  'ap-southeast-6': 'Z01392953RKV2Q3RBP0KU',
  'ap-southeast-7': 'Z048508712PZLK5NKG8R0',
  'ap-northeast-1': 'Z1YSHQZHG15GKL',
  'ap-northeast-2': 'Z20JF4UZKIW1U8',
  'ap-northeast-3': 'Z22ILHG95FLSZ2',
  'eu-west-1': 'ZLY8HYME6SFDD',
  'eu-west-2': 'ZJ5UAJN8Y3Z2Q',
  'eu-west-3': 'Z3KY65QIEKYHQQ',
  'eu-central-1': 'Z1U9ULNL0V5AJ3',
  'eu-central-2': 'Z09222482MK253X48U76H',
  'eu-north-1': 'Z3UWIKFBOOGXPP',
  'eu-south-1': 'Z3BT4WSQ9TDYZV',
  'eu-south-2': 'Z02499852UI5HEQ5JVWX3',
  'il-central-1': 'Z07264553HBI44N5X2CKP',
  'mx-central-1': 'Z00020171WIGL5M88SHRM',
  'me-central-1': 'Z08780021BKYYY8U0YHTV',
  'me-south-1': 'Z20ZBPC0SS8806',
  'sa-east-1': 'ZCMLWB8V5SYIT',
  'us-gov-east-1': 'Z3SE9ATJYCRCZJ',
  'us-gov-west-1': 'Z1K6XKP9SAGWDV',
};

const ELASTICBEANSTALK_ZONE_IDS: Record<string, string> = {
  'us-east-1': 'Z117KPS5GTRQ2G',
  'us-east-2': 'Z14LCN19Q5QHIC',
  'us-west-1': 'Z1LQECGX5PH1X',
  'us-west-2': 'Z38NKT9BP95V3O',
  'ca-central-1': 'ZJFCZL7SSZB5I',
  'ca-west-1': 'Z1021028356Y0CYS11DQI',
  'af-south-1': 'Z1EI3BVKMKK4AM',
  'ap-east-1': 'ZPWYUBWRU171A',
  'ap-south-1': 'Z18NTBI3Y7N9TZ',
  'ap-south-2': 'Z10223522IBWPBF2C2FJS',
  'ap-southeast-1': 'Z16FZ9L249IFLT',
  'ap-southeast-2': 'Z2PCDNR3VC2G1N',
  'ap-southeast-3': 'Z05913172VM7EAZB40TA8',
  'ap-southeast-4': 'Z0666869LC74UHAO5YE4',
  'ap-southeast-5': 'Z01812971H0QCYWSL7WOH',
  'ap-southeast-6': 'Z01144401H1NECCLJDD4D',
  'ap-southeast-7': 'Z08384933QM5LSQCVMNZM',
  'ap-northeast-1': 'Z1R25G3KIG2GBW',
  'ap-northeast-2': 'Z3JE5OI70TWKCP',
  'ap-northeast-3': 'ZNE5GEY1TIAGY',
  'eu-west-1': 'Z2NYPWQ7DFZAZH',
  'eu-west-2': 'Z1GKAAAUGATPF1',
  'eu-west-3': 'Z5WN6GAYWG5OB',
  'eu-central-1': 'Z1FRNW7UH4DEZJ',
  'eu-central-2': 'Z00227012FSHBMZNNSJJI',
  'eu-north-1': 'Z23GO28BZ5AETM',
  'eu-south-1': 'Z10VDYYOA2JFKM',
  'eu-south-2': 'Z0243492AO4B9S3KI68O',
  'il-central-1': 'Z02941091PERNCB1MI5H7',
  'me-central-1': 'Z0650511N84AAKGW7QUK',
  'me-south-1': 'Z2BBTEKR2I36N2',
  'sa-east-1': 'Z10X7K2B4QSOFV',
  'us-gov-east-1': 'Z35TSARG0EJ4VU',
  'us-gov-west-1': 'Z4KAURWC4UUUG',
};

const REGIONAL_TABLES: Record<string, Record<string, string>> = {
  ALB: ALB_ZONE_IDS,
  NLB: NLB_ZONE_IDS,
  S3Website: S3WEBSITE_ZONE_IDS,
  APIGateway: APIGATEWAY_ZONE_IDS,
  ElasticBeanstalk: ELASTICBEANSTALK_ZONE_IDS,
};

export function isGlobalServiceType(serviceType?: string): boolean {
  return !!serviceType && (GLOBAL_SERVICE_TYPES as readonly string[]).includes(serviceType);
}

export function isRegionalServiceType(serviceType?: string): boolean {
  return !!serviceType && serviceType in REGIONAL_TABLES;
}

export function regionsForServiceType(serviceType?: string): string[] {
  if (!serviceType || !(serviceType in REGIONAL_TABLES)) return [];
  return Object.keys(REGIONAL_TABLES[serviceType]);
}

// Mirrors $resolvedAliasZoneId exactly, including the "no match -> empty" fallback that
// causes the platform to reject the record (spec.forProvider.alias.zoneId: null) --
// this function will also return '' in that case, which the preview field renders as a
// visible warning instead of a fake-looking zone ID.
export function resolveAliasZoneId(
  serviceType: string | undefined,
  region: string | undefined,
): string {
  if (!serviceType) return '';
  if (serviceType in GLOBAL_ZONE_IDS) return GLOBAL_ZONE_IDS[serviceType];
  const table = REGIONAL_TABLES[serviceType];
  if (!table || !region) return '';
  return table[region] ?? '';
}
