// TraeCreds - capture the Trae iOS (com.stone.solo.cn) login credentials
// and expose them through an in-app floating panel.
//
// Interaction:
//   three-finger long press inside the app -> floating "T" icon
//   tap the icon                            -> credential panel
//   tap / long-press a row                  -> copy that value
//
// Scope: only requests whose host is a Trae host are inspected. Nothing is
// uploaded anywhere unless you set kRelayBaseURL below. For your own device
// and your own account only.

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <Security/Security.h>

// Optional: POST captured credentials to your relay. Leave empty to disable.
// Example: @"https://your-tunnel.trycloudflare.com"
static NSString *const kRelayBaseURL = @"";

static NSString *const kCredsFile = @"trae-creds.json";

#pragma mark - helpers

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
            for (UIWindow *w in ws.windows) {
                if (w.isKeyWindow) return w;
            }
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

#pragma mark - store

@interface TraeCredStore : NSObject
@property (nonatomic, copy) NSString *token;
@property (nonatomic, copy) NSString *refreshToken;
@property (nonatomic, copy) NSString *userId;
@property (nonatomic, copy) NSString *clientId;
@property (nonatomic, copy) NSString *lastURL;
@property (nonatomic, strong) NSDate *capturedAt;
+ (instancetype)shared;
- (void)noteRequest:(NSURLRequest *)request;
- (void)noteResponse:(NSData *)data forURL:(NSString *)url;
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
            }
        }
    });
    return s;
}

- (void)noteRequest:(NSURLRequest *)request {
    NSString *url = request.URL.absoluteString ?: @"";
    NSString *auth = [request valueForHTTPHeaderField:@"Authorization"];
    NSString *cloudide = [request valueForHTTPHeaderField:@"X-Cloudide-Token"];
    NSString *jwt = nil;

    if ([auth containsString:@"Cloud-IDE-JWT"]) {
        jwt = [[auth componentsSeparatedByString:@" "] lastObject];
    } else if (auth.length > 20 && [auth hasPrefix:@"eyJ"]) {
        jwt = auth;
    } else if (cloudide.length > 20) {
        jwt = cloudide;
    }
    if (jwt.length < 20) return;

    @synchronized (self) {
        self.lastURL = url;
        if (![jwt isEqualToString:self.token]) {
            self.token = jwt;
            self.capturedAt = [NSDate date];
            NSDictionary *payload = DecodeJWT(jwt);
            NSDictionary *data = payload[@"data"];
            if ([data isKindOfClass:NSDictionary.class]) {
                id uid = data[@"id"] ?: data[@"uid"];
                if (uid) self.userId = [uid description];
            }
            [self persist];
        }
    }
}

- (void)noteResponse:(NSData *)data forURL:(NSString *)url {
    if (data.length == 0 || data.length > 2 * 1024 * 1024) return;
    NSString *l = url.lowercaseString;
    if (!([l containsString:@"token"] || [l containsString:@"auth"] ||
          [l containsString:@"login"] || [l containsString:@"session"])) return;

    id obj = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if (![obj isKindOfClass:NSDictionary.class]) return;

    BOOL changed = NO;
    NSMutableArray *stack = [NSMutableArray arrayWithObject:obj];
    while (stack.count) {
        id cur = stack.lastObject;
        [stack removeLastObject];
        if ([cur isKindOfClass:NSDictionary.class]) {
            for (id k in [(NSDictionary *)cur allKeys]) {
                id v = cur[k];
                NSString *key = [k description].lowercaseString;
                if ([v isKindOfClass:NSString.class] && [v length] > 16) {
                    if ([key isEqualToString:@"refreshtoken"] || [key isEqualToString:@"refresh_token"]) {
                        if (![v isEqualToString:self.refreshToken]) { self.refreshToken = v; changed = YES; }
                    } else if (([key isEqualToString:@"token"] || [key isEqualToString:@"accesstoken"] ||
                                [key isEqualToString:@"cloudidetoken"]) && [v hasPrefix:@"eyJ"]) {
                        if (!self.token) { self.token = v; changed = YES; }
                    } else if ([key isEqualToString:@"userid"] || [key isEqualToString:@"uid"]) {
                        if (!self.userId) { self.userId = v; changed = YES; }
                    } else if ([key isEqualToString:@"clientid"] || [key isEqualToString:@"client_id"]) {
                        if (![v isEqualToString:self.clientId]) { self.clientId = v; changed = YES; }
                    }
                } else if ([v isKindOfClass:NSDictionary.class] || [v isKindOfClass:NSArray.class]) {
                    [stack addObject:v];
                }
            }
        } else if ([cur isKindOfClass:NSArray.class]) {
            [stack addObjectsFromArray:cur];
        }
    }
    if (changed) [self persist];
}

- (NSDictionary *)snapshot {
    @synchronized (self) {
        if (self.token.length < 20) return nil;
        return @{ @"token": self.token ?: @"",
                  @"refreshToken": self.refreshToken ?: @"",
                  @"userId": self.userId ?: @"",
                  @"clientId": self.clientId ?: @"ono9krqynydwx5",
                  @"source": self.lastURL ?: @"" };
    }
}

- (void)persist {
    NSDictionary *snap = [self snapshot];
    if (!snap) return;
    NSData *json = [NSJSONSerialization dataWithJSONObject:snap options:NSJSONWritingPrettyPrinted error:nil];
    [json writeToFile:DocsPath() atomically:YES];
    UIPasteboard.generalPasteboard.string = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];

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

#pragma mark - panel

@interface TraeCredsPanel : UIViewController <UITableViewDataSource, UITableViewDelegate>
@property (nonatomic, strong) NSDictionary *creds;
@property (nonatomic, strong) NSArray<NSString *> *rows;
@end

@implementation TraeCredsPanel

- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"Trae 凭据";
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.rows = @[@"token", @"refreshToken", @"userId", @"clientId", @"source"];

    UITableView *tv = [[UITableView alloc] initWithFrame:self.view.bounds style:UITableViewStyleInsetGrouped];
    tv.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    tv.dataSource = self;
    tv.delegate = self;
    [self.view addSubview:tv];

    self.navigationItem.rightBarButtonItem =
        [[UIBarButtonItem alloc] initWithTitle:@"关闭" style:UIBarButtonItemStyleDone
                                        target:self action:@selector(close)];
    self.navigationItem.leftBarButtonItem =
        [[UIBarButtonItem alloc] initWithTitle:@"复制全部" style:UIBarButtonItemStylePlain
                                        target:self action:@selector(copyAll)];
}

- (void)close { [self dismissViewControllerAnimated:YES completion:nil]; }

- (void)copyAll {
    if (!self.creds) return;
    NSData *json = [NSJSONSerialization dataWithJSONObject:self.creds options:NSJSONWritingPrettyPrinted error:nil];
    UIPasteboard.generalPasteboard.string = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
    [self toast:@"已复制完整 JSON"];
}

- (void)toast:(NSString *)text {
    UILabel *l = [UILabel new];
    l.text = text;
    l.font = [UIFont systemFontOfSize:14 weight:UIFontWeightMedium];
    l.textColor = UIColor.whiteColor;
    l.backgroundColor = [UIColor colorWithWhite:0 alpha:0.8];
    l.textAlignment = NSTextAlignmentCenter;
    l.layer.cornerRadius = 10;
    l.clipsToBounds = YES;
    [l sizeToFit];
    CGRect f = l.frame;
    f.size.width += 32; f.size.height += 18;
    l.frame = f;
    l.center = CGPointMake(self.view.bounds.size.width / 2, self.view.bounds.size.height - 90);
    l.autoresizingMask = UIViewAutoresizingFlexibleTopMargin | UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleRightMargin;
    [self.view addSubview:l];
    [UIView animateWithDuration:0.25 animations:^{ l.alpha = 0; } completion:^(BOOL done) { [l removeFromSuperview]; }];
}

- (NSInteger)tableView:(UITableView *)tv numberOfRowsInSection:(NSInteger)section { return self.rows.count; }

- (NSString *)valueForRow:(NSInteger)row {
    NSString *key = self.rows[row];
    id v = self.creds[key];
    if (!v) return @"（未捕获）";
    return [v description];
}

- (UITableViewCell *)tableView:(UITableView *)tv cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [tv dequeueReusableCellWithIdentifier:@"c"];
    if (!cell) cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:@"c"];
    NSString *key = self.rows[indexPath.row];
    NSString *val = [self valueForRow:indexPath.row];
    cell.textLabel.text = key;
    cell.detailTextLabel.text = val.length > 90 ? [[val substringToIndex:90] stringByAppendingString:@"…"] : val;
    cell.detailTextLabel.numberOfLines = 2;
    cell.detailTextLabel.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    cell.accessoryType = UITableViewCellAccessoryNone;
    return cell;
}

- (void)tableView:(UITableView *)tv didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tv deselectRowAtIndexPath:indexPath animated:YES];
    NSString *val = [self valueForRow:indexPath.row];
    UIPasteboard.generalPasteboard.string = val;
    [self toast:[NSString stringWithFormat:@"已复制 %@", self.rows[indexPath.row]]];
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
    if (!win) { dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{ [self install]; }); return; }
    for (UIGestureRecognizer *g in win.gestureRecognizers) {
        if ([g isKindOfClass:UILongPressGestureRecognizer.class] && ((UILongPressGestureRecognizer *)g).numberOfTouchesRequired == 3) return;
    }
    UILongPressGestureRecognizer *lp = [[UILongPressGestureRecognizer alloc] initWithTarget:self action:@selector(onLongPress:)];
    lp.numberOfTouchesRequired = 3;
    lp.minimumPressDuration = 0.8;
    lp.delegate = self;
    [win addGestureRecognizer:lp];
    NSLog(@"[TraeCreds] 3-finger long press installed");
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

    UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(onPan:)];
    [b addGestureRecognizer:pan];
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

- (void)hideIcon {
    [self.icon removeFromSuperview];
    self.icon = nil;
}

- (void)openPanel {
    NSDictionary *snap = [[TraeCredStore shared] snapshot];
    TraeCredsPanel *p = [TraeCredsPanel new];
    p.creds = snap ?: @{};
    UINavigationController *nav = [[UINavigationController alloc] initWithRootViewController:p];
    nav.modalPresentationStyle = UIModalPresentationPageSheet;
    UIViewController *top = TraeTopController();
    if (top) [top presentViewController:nav animated:YES completion:nil];
}

@end

#pragma mark - hooks

%hook NSURLSession

- (NSURLSessionDataTask *)dataTaskWithRequest:(NSURLRequest *)request
                            completionHandler:(void (^)(NSData *, NSURLResponse *, NSError *))handler {
    NSString *url = request.URL.absoluteString;
    if (TraeHost(url)) {
        @try { [[TraeCredStore shared] noteRequest:request]; } @catch (NSException *e) {}
        if (handler) {
            void (^wrapped)(NSData *, NSURLResponse *, NSError *) = ^(NSData *data, NSURLResponse *resp, NSError *err) {
                @try { [[TraeCredStore shared] noteResponse:data forURL:url]; } @catch (NSException *e) {}
                handler(data, resp, err);
            };
            return %orig(request, wrapped);
        }
    }
    return %orig;
}

%end

%hook NSMutableURLRequest

- (void)setValue:(NSString *)value forHTTPHeaderField:(NSString *)field {
    %orig;
    @try {
        if (TraeHost(self.URL.absoluteString) &&
            ([field.lowercaseString isEqualToString:@"authorization"] ||
             [field.lowercaseString isEqualToString:@"x-cloudide-token"])) {
            [[TraeCredStore shared] noteRequest:self];
        }
    } @catch (NSException *e) {}
}

%end

%hookf(OSStatus, SecItemAdd, CFDictionaryRef attributes, CFTypeRef *result) {
    OSStatus status = %orig;
    @try {
        NSDictionary *dict = (__bridge NSDictionary *)attributes;
        NSString *svc = dict[(__bridge id)kSecAttrService];
        NSString *acct = dict[(__bridge id)kSecAttrAccount];
        if ([svc.lowercaseString containsString:@"trae"] || [svc.lowercaseString containsString:@"solo"] ||
            [acct.lowercaseString containsString:@"trae"]) {
            NSLog(@"[TraeCreds] keychain add svc=%@ acct=%@", svc, acct);
        }
    } @catch (NSException *e) {}
    return status;
}

%ctor {
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(2.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        [[TraeOverlay shared] install];
    });
}
