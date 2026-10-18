// TraeCreds - capture Trae iOS (com.stone.solo.cn) login credentials.
//
// The app uses ByteDance TTNet (Cronet + BoringSSL), NOT NSURLSession, so the
// previous NSURLSession-only hooks never fired. This version hooks BoringSSL
// at the plaintext layer and adds a Keychain / NSUserDefaults fallback.
//
// Interaction: three-finger long press -> floating "T" -> credential panel.

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <Security/Security.h>
#import <substrate.h>
#import <dlfcn.h>

static NSString *const kRelayBaseURL = @"";   // optional: POST creds to relay
static NSString *const kCredsFile = @"trae-creds.json";

#pragma mark - small helpers

static BOOL TraeHost(NSString *url) {
    if (url.length == 0) return NO;
    NSString *l = url.lowercaseString;
    return [l containsString:@"trae.cn"] ||
           [l containsString:@"trae-api-cn"] ||
           [l containsString:@"mchost.guru"];
}

static NSDictionary *DecodeJWT(NSString *jwt) {
    NSArray *parts = [jwt componentsSeparatedByString:@"."];
    if (parts.count < 2) return nil;
    NSString *p = parts[1];
    p = [p stringByReplacingOccurrencesOfString:@"-" withString:@"+"];
    p = [p stringByReplacingOccurrencesOfString:@"_" withString:@"/"];
    while (p.length % 4) p = [p stringByAppendingString:@"="];
    NSData *d = [[NSData alloc] initWithBase64EncodedString:p options:0];
    if (!d) return nil;
    return [NSJSONSerialization JSONObjectWithData:d options:0 error:nil];
}

static NSString *DocsPath(void) {
    NSString *dir = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    return [dir stringByAppendingPathComponent:kCredsFile];
}

static UIWindow *TraeKeyWindow(void) {
    if (@available(iOS 13.0, *)) {
        for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
            if (![scene isKindOfClass:UIWindowScene.class]) continue;
            UIWindowScene *ws = (UIWindowScene *)scene;
            for (UIWindow *w in ws.windows) if (w.isKeyWindow) return w;
            if (ws.windows.count > 0) return ws.windows.firstObject;
        }
    }
    return nil;
}

static UIViewController *TraeTopController(void) {
    UIViewController *top = TraeKeyWindow().rootViewController;
    while (top.presentedViewController) top = top.presentedViewController;
    return top;
}

#pragma mark - plaintext scanner

static NSString *JWTFromBytes(const uint8_t *buf, size_t len, size_t *outLen) {
    if (len < 32) return nil;
    for (size_t i = 0; i + 3 < len; i++) {
        if (buf[i] == 'e' && buf[i+1] == 'y' && buf[i+2] == 'J') {
            size_t j = i;
            while (j < len && j - i < 4096) {
                uint8_t c = buf[j];
                BOOL ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                          (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.';
                if (!ok) break;
                j++;
            }
            size_t n = j - i;
            if (n > 60) {
                NSString *s = [[NSString alloc] initWithBytes:buf + i length:n encoding:NSASCIIStringEncoding];
                if ([s componentsSeparatedByString:@"."].count >= 3) {
                    if (outLen) *outLen = n;
                    return s;
                }
            }
            i = j;
        }
    }
    return nil;
}

// Find  "key" : "value"  (or key=value) inside a byte buffer and return value.
static NSString *JSONValueFor(const uint8_t *buf, size_t len, const char *key) {
    size_t klen = strlen(key);
    if (len < klen + 8) return nil;
    for (size_t i = 0; i + klen < len; i++) {
        if (memcmp(buf + i, key, klen) != 0) continue;
        size_t j = i + klen;
        while (j < len && (buf[j] == '"' || buf[j] == ' ' || buf[j] == ':' || buf[j] == '=' || buf[j] == '\t')) j++;
        if (j >= len || buf[j] != '"') continue;
        j++;
        size_t start = j;
        while (j < len && j - start < 2048) {
            if (buf[j] == '"' || buf[j] == '\n' || buf[j] == '\r') break;
            j++;
        }
        if (j > start + 8) {
            return [[NSString alloc] initWithBytes:buf + start length:(j - start) encoding:NSUTF8StringEncoding];
        }
    }
    return nil;
}

#pragma mark - store

@interface TraeCredStore : NSObject
@property (nonatomic, copy) NSString *token;
@property (nonatomic, copy) NSString *refreshToken;
@property (nonatomic, copy) NSString *userId;
@property (nonatomic, copy) NSString *clientId;
@property (nonatomic, copy) NSString *source;
@property (nonatomic, strong) NSDate *capturedAt;
+ (instancetype)shared;
- (void)ingestBytes:(const uint8_t *)buf length:(size_t)len label:(NSString *)label;
- (void)scanKeychain;
- (void)scanDefaults;
- (NSDictionary *)snapshot;
@end

@implementation TraeCredStore

+ (instancetype)shared {
    static TraeCredStore *s;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        s = [TraeCredStore new];
        s.clientId = @"ono9krqynydwx5";
        NSData *old = [NSData dataWithContentsOfFile:DocsPath()];
        if (old) {
            NSDictionary *d = [NSJSONSerialization JSONObjectWithData:old options:0 error:nil];
            if ([d isKindOfClass:NSDictionary.class]) {
                s.token = d[@"token"]; s.refreshToken = d[@"refreshToken"];
                s.userId = d[@"userId"]; s.clientId = d[@"clientId"] ?: s.clientId;
                s.source = d[@"source"];
            }
        }
    });
    return s;
}

- (void)ingestBytes:(const uint8_t *)buf length:(size_t)len label:(NSString *)label {
    if (!buf || len < 16 || len > 4 * 1024 * 1024) return;
    BOOL changed = NO;

    NSString *jwt = JWTFromBytes(buf, len, NULL);
    if (jwt && ![jwt isEqualToString:self.token]) {
        self.token = jwt;
        self.capturedAt = [NSDate date];
        self.source = label;
        changed = YES;
        NSDictionary *payload = DecodeJWT(jwt);
        NSDictionary *data = payload[@"data"];
        if ([data isKindOfClass:NSDictionary.class]) {
            id uid = data[@"id"] ?: data[@"uid"];
            if (uid) self.userId = [uid description];
        }
    }

    if (!self.refreshToken) {
        NSString *r = JSONValueFor(buf, len, "\"RefreshToken\"");
        if (!r) r = JSONValueFor(buf, len, "\"refreshToken\"");
        if (!r) r = JSONValueFor(buf, len, "\"refresh_token\"");
        if (r.length > 12) { self.refreshToken = r; changed = YES; }
    }
    if (!self.userId) {
        NSString *u = JSONValueFor(buf, len, "\"UserID\"");
        if (!u) u = JSONValueFor(buf, len, "\"userId\"");
        if (u.length > 2) { self.userId = u; changed = YES; }
    }
    if (!self.clientId) {
        NSString *c = JSONValueFor(buf, len, "\"ClientID\"");
        if (c.length > 2) { self.clientId = c; changed = YES; }
    }

    if (changed) [self persist];
}

- (void)scanKeychain {
    NSDictionary *q = @{ (__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
                         (__bridge id)kSecReturnAttributes: @YES,
                         (__bridge id)kSecReturnData: @YES,
                         (__bridge id)kSecMatchLimit: (__bridge id)kSecMatchLimitAll };
    CFTypeRef result = NULL;
    if (SecItemCopyMatching((__bridge CFDictionaryRef)q, &result) != errSecSuccess || !result) return;
    NSArray *items = (__bridge_transfer NSArray *)result;
    for (id item in items) {
        if (![item isKindOfClass:NSDictionary.class]) continue;
        NSData *data = item[(__bridge id)kSecValueData];
        if (![data isKindOfClass:NSData.class] || data.length == 0) continue;
        NSString *svc = item[(__bridge id)kSecAttrService] ?: @"";
        [self ingestBytes:data.bytes length:data.length label:[@"keychain:" stringByAppendingString:svc]];
        // base64-wrapped payloads
        NSString *b64 = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
        if (b64.length && b64.length < 20000) {
            NSData *decoded = [[NSData alloc] initWithBase64EncodedString:b64 options:0];
            if (decoded) [self ingestBytes:decoded.bytes length:decoded.length label:@"keychain-b64"];
        }
    }
}

- (void)scanDefaults {
    NSDictionary *d = [NSUserDefaults.standardUserDefaults dictionaryRepresentation];
    for (NSString *k in d) {
        id v = d[k];
        if ([v isKindOfClass:NSString.class]) {
            NSData *data = [(NSString *)v dataUsingEncoding:NSUTF8StringEncoding];
            [self ingestBytes:data.bytes length:data.length label:[@"defaults:" stringByAppendingString:k]];
        } else if ([v isKindOfClass:NSData.class]) {
            [self ingestBytes:((NSData *)v).bytes length:((NSData *)v).length label:@"defaults-data"];
        }
    }
}

- (NSDictionary *)snapshot {
    @synchronized (self) {
        if (self.token.length < 20 && self.refreshToken.length < 12) return nil;
        return @{ @"token": self.token ?: @"",
                  @"refreshToken": self.refreshToken ?: @"",
                  @"userId": self.userId ?: @"",
                  @"clientId": self.clientId ?: @"ono9krqynydwx5",
                  @"source": self.source ?: @"" };
    }
}

- (void)persist {
    NSDictionary *snap = [self snapshot];
    if (!snap) return;
    NSData *json = [NSJSONSerialization dataWithJSONObject:snap options:NSJSONWritingPrettyPrinted error:nil];
    [json writeToFile:DocsPath() atomically:YES];

    if (kRelayBaseURL.length) {
        NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:
            [NSURL URLWithString:[kRelayBaseURL stringByAppendingString:@"/api/web-auth"]]];
        req.HTTPMethod = @"POST";
        [req setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
        req.HTTPBody = json;
        [[NSURLSession.sharedSession dataTaskWithRequest:req] resume];
    }
}

@end

#pragma mark - SSL hooks (TTNet / Cronet use BoringSSL)

static int (*orig_SSL_write)(void *, const void *, int);
static int (*orig_SSL_read)(void *, void *, int);

static int hook_SSL_write(void *ssl, const void *buf, int num) {
    @try { [[TraeCredStore shared] ingestBytes:buf length:num label:@"ssl-write"]; } @catch (NSException *e) {}
    return orig_SSL_write(ssl, buf, num);
}

static int hook_SSL_read(void *ssl, void *buf, int num) {
    int n = orig_SSL_read(ssl, buf, num);
    if (n > 0) {
        @try { [[TraeCredStore shared] ingestBytes:buf length:(size_t)n label:@"ssl-read"]; } @catch (NSException *e) {}
    }
    return n;
}

#pragma mark - panel

@interface TraeCredsPanel : UIViewController <UITableViewDataSource, UITableViewDelegate>
@property (nonatomic, strong) NSDictionary *creds;
@property (nonatomic, strong) NSArray<NSString *> *rows;
@property (nonatomic, strong) UILabel *empty;
@end

@implementation TraeCredsPanel

- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"Trae 凭据";
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.rows = @[@"token", @"refreshToken", @"userId", @"clientId", @"source"];

    UITableView *tv = [[UITableView alloc] initWithFrame:self.view.bounds style:UITableViewStyleInsetGrouped];
    tv.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    tv.dataSource = self; tv.delegate = self;
    [self.view addSubview:tv];

    self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:@"关闭" style:UIBarButtonItemStyleDone target:self action:@selector(close)];
    self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:@"重新扫描" style:UIBarButtonItemStylePlain target:self action:@selector(rescan)];
}

- (void)close { [self dismissViewControllerAnimated:YES completion:nil]; }

- (void)rescan {
    [[TraeCredStore shared] scanKeychain];
    [[TraeCredStore shared] scanDefaults];
    self.creds = [[TraeCredStore shared] snapshot] ?: @{};
    [self reload];
}

- (void)reload {
    UITableView *tv = nil;
    for (UIView *v in self.view.subviews) if ([v isKindOfClass:UITableView.class]) tv = (UITableView *)v;
    [tv reloadData];
}

- (NSInteger)tableView:(UITableView *)tv numberOfRowsInSection:(NSInteger)section { return self.rows.count; }

- (NSString *)valueForRow:(NSInteger)row {
    id v = self.creds[self.rows[row]];
    return v ? [v description] : @"（未捕获）";
}

- (UITableViewCell *)tableView:(UITableView *)tv cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [tv dequeueReusableCellWithIdentifier:@"c"];
    if (!cell) cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:@"c"];
    NSString *val = [self valueForRow:indexPath.row];
    cell.textLabel.text = self.rows[indexPath.row];
    cell.detailTextLabel.text = val.length > 90 ? [[val substringToIndex:90] stringByAppendingString:@"…"] : val;
    cell.detailTextLabel.numberOfLines = 2;
    cell.detailTextLabel.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    cell.detailTextLabel.textColor = [val isEqualToString:@"（未捕获）"] ? UIColor.systemGrayColor : UIColor.labelColor;
    return cell;
}

- (void)tableView:(UITableView *)tv didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tv deselectRowAtIndexPath:indexPath animated:YES];
    NSString *val = [self valueForRow:indexPath.row];
    UIPasteboard.generalPasteboard.string = val;
}

@end

#pragma mark - overlay

@interface TraeOverlay : NSObject <UIGestureRecognizerDelegate>
@property (nonatomic, strong) UIButton *icon;
+ (instancetype)shared;
- (void)install;
- (void)showIcon;
- (void)hideIcon;
- (void)openPanel;
@end

@implementation TraeOverlay

+ (instancetype)shared {
    static TraeOverlay *s;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ s = [TraeOverlay new]; });
    return s;
}

- (void)install {
    UIWindow *win = TraeKeyWindow();
    if (!win) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{ [self install]; });
        return;
    }
    for (UIGestureRecognizer *g in win.gestureRecognizers) {
        if ([g isKindOfClass:UILongPressGestureRecognizer.class] && ((UILongPressGestureRecognizer *)g).numberOfTouchesRequired == 3) return;
    }
    UILongPressGestureRecognizer *lp = [[UILongPressGestureRecognizer alloc] initWithTarget:self action:@selector(onLongPress:)];
    lp.numberOfTouchesRequired = 3;
    lp.minimumPressDuration = 0.8;
    lp.delegate = self;
    [win addGestureRecognizer:lp];
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer *)g shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer *)other { return YES; }

- (void)onLongPress:(UILongPressGestureRecognizer *)g {
    if (g.state != UIGestureRecognizerStateBegan) return;
    [self showIcon];
    UIImpactFeedbackGenerator *h = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleMedium];
    [h impactOccurred];
}

- (void)showIcon {
    if (self.icon) { self.icon.hidden = NO; return; }
    UIWindow *win = TraeKeyWindow();
    if (!win) return;
    UIButton *b = [UIButton buttonWithType:UIButtonTypeCustom];
    b.frame = CGRectMake(16, 120, 46, 46);
    b.layer.cornerRadius = 23;
    b.backgroundColor = [UIColor colorWithRed:0.18 green:0.49 blue:0.96 alpha:0.92];
    b.layer.shadowColor = UIColor.blackColor.CGColor;
    b.layer.shadowOpacity = 0.25;
    b.layer.shadowRadius = 6;
    b.layer.shadowOffset = CGSizeMake(0, 2);
    [b setTitle:@"T" forState:UIControlStateNormal];
    b.titleLabel.font = [UIFont boldSystemFontOfSize:20];
    [b setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    [b addTarget:self action:@selector(openPanel) forControlEvents:UIControlEventTouchUpInside];
    [b addGestureRecognizer:[[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(onPan:)]];
    UILongPressGestureRecognizer *hide = [[UILongPressGestureRecognizer alloc] initWithTarget:self action:@selector(onIconLongPress:)];
    [b addGestureRecognizer:hide];
    [win addSubview:b];
    self.icon = b;
}

- (void)onPan:(UIPanGestureRecognizer *)p {
    UIView *v = p.view;
    CGPoint t = [p translationInView:v.superview];
    v.center = CGPointMake(v.center.x + t.x, v.center.y + t.y);
    [p setTranslation:CGPointZero inView:v.superview];
}

- (void)onIconLongPress:(UILongPressGestureRecognizer *)g {
    if (g.state != UIGestureRecognizerStateBegan) return;
    [self hideIcon];
}

- (void)hideIcon { [self.icon removeFromSuperview]; self.icon = nil; }

- (void)openPanel {
    [[TraeCredStore shared] scanKeychain];
    [[TraeCredStore shared] scanDefaults];
    TraeCredsPanel *p = [TraeCredsPanel new];
    p.creds = [[TraeCredStore shared] snapshot] ?: @{};
    UINavigationController *nav = [[UINavigationController alloc] initWithRootViewController:p];
    nav.modalPresentationStyle = UIModalPresentationPageSheet;
    UIViewController *top = TraeTopController();
    if (top) [top presentViewController:nav animated:YES completion:nil];
}

@end

#pragma mark - legacy NSURLSession hooks (kept as a fallback)

%hook NSURLSession

- (NSURLSessionDataTask *)dataTaskWithRequest:(NSURLRequest *)request
                            completionHandler:(void (^)(NSData *, NSURLResponse *, NSError *))handler {
    NSString *url = request.URL.absoluteString;
    if (TraeHost(url)) {
        NSMutableData *head = [NSMutableData data];
        [head appendData:[url dataUsingEncoding:NSUTF8StringEncoding]];
        for (NSString *f in @[@"Authorization", @"X-Cloudide-Token", @"Cookie"]) {
            NSString *v = [request valueForHTTPHeaderField:f];
            if (v) [head appendData:[[NSString stringWithFormat:@"\n%@: %@", f, v] dataUsingEncoding:NSUTF8StringEncoding]];
        }
        @try { [[TraeCredStore shared] ingestBytes:head.bytes length:head.length label:@"nsurlsession"]; } @catch (NSException *e) {}
        if (handler) {
            void (^wrapped)(NSData *, NSURLResponse *, NSError *) = ^(NSData *data, NSURLResponse *resp, NSError *err) {
                @try { [[TraeCredStore shared] ingestBytes:data.bytes length:data.length label:@"nsurlsession-resp"]; } @catch (NSException *e) {}
                handler(data, resp, err);
            };
            return %orig(request, wrapped);
        }
    }
    return %orig;
}

%end

#pragma mark - install

%ctor {
    // BoringSSL hooks: the app's real transport is TTNet/Cronet.
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        void *w = dlsym(RTLD_DEFAULT, "SSL_write");
        void *r = dlsym(RTLD_DEFAULT, "SSL_read");
        if (w) MSHookFunction(w, (void *)hook_SSL_write, (void **)&orig_SSL_write);
        if (r) MSHookFunction(r, (void *)hook_SSL_read, (void **)&orig_SSL_read);
        NSLog(@"[TraeCreds] SSL hooks: write=%p read=%p", w, r);
    });

    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(2.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        [[TraeOverlay shared] install];
        [[TraeCredStore shared] scanKeychain];
        [[TraeCredStore shared] scanDefaults];
    });
}
