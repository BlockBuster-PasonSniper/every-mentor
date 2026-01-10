@file:OptIn(ExperimentalMaterial3Api::class)

package com.example.everymentor

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.foundation.BorderStroke
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.boundsInRoot
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import androidx.navigation.compose.*
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import kotlin.math.abs

// -----------------------------
// DataStore (로컬 저장)
// -----------------------------
private val ComponentActivity.dataStore by preferencesDataStore(name = "mentee_prefs")

private object PrefKeys {
    val LOGGED_IN = booleanPreferencesKey("logged_in")
    val ROLE = stringPreferencesKey("role") // "mentee" or "mentor"
    val HAS_PROFILE = booleanPreferencesKey("has_profile")

    val PROFILE_NAME = stringPreferencesKey("profile_name")
    val PROFILE_BIO = stringPreferencesKey("profile_bio")
    val PROFILE_PUBLIC = booleanPreferencesKey("profile_public")
    val PROFILE_PHOTO_URI = stringPreferencesKey("profile_photo_uri")

    val MATCHED_COURSE_ID = stringPreferencesKey("matched_course_id") // null이면 미매칭
    val MY_COURSE_IDS = stringPreferencesKey("my_course_ids") // comma-separated
}

class MenteePrefs(private val activity: ComponentActivity) {
    private val ds = activity.dataStore

    suspend fun setLogin(role: String) {
        ds.edit {
            it[PrefKeys.LOGGED_IN] = true
            it[PrefKeys.ROLE] = role
        }
    }

    suspend fun logout() {
        ds.edit { it.clear() }
    }

    val roleFlow = ds.data.map { it[PrefKeys.ROLE] ?: "" }
    val loggedInFlow = ds.data.map { it[PrefKeys.LOGGED_IN] ?: false }
    val hasProfileFlow = ds.data.map { it[PrefKeys.HAS_PROFILE] ?: false }
    val matchedCourseIdFlow = ds.data.map { it[PrefKeys.MATCHED_COURSE_ID] } // String? 가능

    val profileFlow = ds.data.map {
        MenteeProfile(
            name = it[PrefKeys.PROFILE_NAME] ?: "",
            bio = it[PrefKeys.PROFILE_BIO] ?: "",
            isPublic = it[PrefKeys.PROFILE_PUBLIC] ?: true,
            photoUri = it[PrefKeys.PROFILE_PHOTO_URI] ?: ""
        )
    }

    suspend fun saveProfile(profile: MenteeProfile) {
        ds.edit {
            it[PrefKeys.PROFILE_NAME] = profile.name
            it[PrefKeys.PROFILE_BIO] = profile.bio
            it[PrefKeys.PROFILE_PUBLIC] = profile.isPublic
            it[PrefKeys.PROFILE_PHOTO_URI] = profile.photoUri
            it[PrefKeys.HAS_PROFILE] = true
        }
    }

    suspend fun setMatchedCourse(courseId: String?) {
        ds.edit {
            if (courseId == null) it.remove(PrefKeys.MATCHED_COURSE_ID)
            else it[PrefKeys.MATCHED_COURSE_ID] = courseId
        }
    }

    suspend fun getMyCourseIds(): List<String> {
        val raw = ds.data.first()[PrefKeys.MY_COURSE_IDS].orEmpty()
        return raw.split(",").map { it.trim() }.filter { it.isNotEmpty() }
    }

    suspend fun setMyCourseIds(ids: List<String>) {
        ds.edit { it[PrefKeys.MY_COURSE_IDS] = ids.joinToString(",") }
    }

    suspend fun addMyCourseId(id: String) {
        val current = getMyCourseIds().toMutableList()
        if (!current.contains(id)) current.add(id)
        setMyCourseIds(current)
    }
}

// -----------------------------
// Models
// -----------------------------
data class MenteeProfile(
    val name: String,
    val bio: String,
    val isPublic: Boolean,
    val photoUri: String
)

data class Course(
    val id: String,
    val mentorDisplayName: String,
    val title: String,
    val summary: String,
    val detail: String,
    val tags: List<String>
)

// -----------------------------
// Repository (API 붙일 자리 비워두기)
// -----------------------------
interface CourseRepository {
    suspend fun loadAllCourses(): List<Course>
}

class FakeCourseRepository : CourseRepository {
    override suspend fun loadAllCourses(): List<Course> {
        return listOf(
            Course(
                id = "c1",
                mentorDisplayName = "멘토 A",
                title = "코틀린 기초부터 앱 출시까지",
                summary = "초보자용, 실습 중심",
                detail = "Kotlin 문법 → Compose UI → 상태관리 → 배포까지 순서대로 진행합니다.",
                tags = listOf("Kotlin", "Android", "Compose")
            ),
            Course(
                id = "c2",
                mentorDisplayName = "멘토 B",
                title = "면접 대비 CS 압축 코스",
                summary = "자료구조/네트워크/OS 핵심",
                detail = "주 2회 라이브 Q&A와 모의면접을 포함합니다.",
                tags = listOf("CS", "Interview", "Q&A")
            ),
            Course(
                id = "c3",
                mentorDisplayName = "멘토 C",
                title = "프로젝트 포트폴리오 리뷰",
                summary = "이력서/깃허브/발표자료 피드백",
                detail = "멘티가 가진 프로젝트를 기반으로 개선 포인트를 같이 잡습니다.",
                tags = listOf("Portfolio", "Review")
            ),
            Course(
                id = "c4",
                mentorDisplayName = "멘토 D",
                title = "알고리즘 문제풀이 루틴 만들기",
                summary = "매일 30분 루틴 설계",
                detail = "레벨별 문제 추천과 풀이 습관을 잡아주는 코스입니다.",
                tags = listOf("Algorithm", "Routine")
            )
        )
    }
}

// -----------------------------
// Navigation Destinations
// -----------------------------
private object Dest {
    const val LOGIN = "login"          // 여기서 "자동 로그인" 처리만 하고 넘어감
    const val ROUTER = "router"
    const val PROFILE_CREATE = "profile_create"
    const val MATCH = "match"
    const val SEARCH = "search"
    const val MY_COURSES = "my_courses"
}

// -----------------------------
// MainActivity
// -----------------------------
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val prefs = MenteePrefs(this)
        val repo: CourseRepository = FakeCourseRepository()

        setContent {
            MaterialTheme {
                val nav = rememberNavController()

                NavHost(navController = nav, startDestination = Dest.LOGIN) {

                    // ✅ 로그인 화면 스킵: 자동으로 멘티 로그인 처리 후 ROUTER로 이동
                    composable(Dest.LOGIN) {
                        LaunchedEffect(Unit) {
                            prefs.setLogin("mentee")
                            nav.navigate(Dest.ROUTER) {
                                popUpTo(Dest.LOGIN) { inclusive = true }
                            }
                        }
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    }

                    composable(Dest.ROUTER) {
                        RouterScreen(
                            prefs = prefs,
                            onGoProfileCreate = {
                                nav.navigate(Dest.PROFILE_CREATE) {
                                    popUpTo(Dest.ROUTER) { inclusive = true }
                                }
                            },
                            onGoMatch = {
                                nav.navigate(Dest.MATCH) {
                                    popUpTo(Dest.ROUTER) { inclusive = true }
                                }
                            },
                            onGoMyCourses = {
                                nav.navigate(Dest.MY_COURSES) {
                                    popUpTo(Dest.ROUTER) { inclusive = true }
                                }
                            }
                        )
                    }

                    composable(Dest.PROFILE_CREATE) {
                        ProfileCreateScreen(
                            prefs = prefs,
                            onDone = {
                                nav.navigate(Dest.MATCH) {
                                    popUpTo(Dest.PROFILE_CREATE) { inclusive = true }
                                }
                            }
                        )
                    }

                    composable(Dest.MATCH) {
                        MatchScreen(
                            prefs = prefs,
                            repo = repo,
                            onGoSearch = { nav.navigate(Dest.SEARCH) },
                            onGoMyCourses = { nav.navigate(Dest.MY_COURSES) }
                        )
                    }

                    composable(Dest.SEARCH) {
                        SearchScreen(repo = repo, onBack = { nav.popBackStack() })
                    }

                    composable(Dest.MY_COURSES) {
                        MyCoursesScreen(
                            prefs = prefs,
                            repo = repo,
                            onBack = { nav.popBackStack() },
                            onGoMatch = { nav.navigate(Dest.MATCH) }
                        )
                    }
                }
            }
        }
    }
}

// -----------------------------
// Screens
// -----------------------------
@Composable
private fun RouterScreen(
    prefs: MenteePrefs,
    onGoProfileCreate: () -> Unit,
    onGoMatch: () -> Unit,
    onGoMyCourses: () -> Unit
) {
    val role by prefs.roleFlow.collectAsState(initial = "")
    val hasProfile by prefs.hasProfileFlow.collectAsState(initial = false)
    val matchedCourseId by prefs.matchedCourseIdFlow.collectAsState(initial = null)

    LaunchedEffect(role, hasProfile, matchedCourseId) {
        if (role.isBlank()) return@LaunchedEffect

        if (role != "mentee") {
            onGoMatch()
            return@LaunchedEffect
        }
        if (!hasProfile) onGoProfileCreate()
        else if (matchedCourseId == null) onGoMatch()
        else onGoMyCourses()
    }

    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

@Composable
private fun ProfileCreateScreen(
    prefs: MenteePrefs,
    onDone: () -> Unit
) {
    val scope = rememberCoroutineScope()

    var name by remember { mutableStateOf("") }
    var bio by remember { mutableStateOf("") }
    var isPublic by remember { mutableStateOf(true) }

    Scaffold(
        topBar = { TopAppBar(title = { Text("멘티 프로필 생성") }) }
    ) { pad ->
        Column(
            Modifier
                .padding(pad)
                .fillMaxSize()
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            OutlinedTextField(
                value = name,
                onValueChange = { name = it },
                label = { Text("이름") },
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = bio,
                onValueChange = { bio = it },
                label = { Text("간략 소개/신상정보") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 3
            )

            AssistChip(
                onClick = { /* TODO: 사진 선택 */ },
                label = { Text("사진 선택 (프로토타입: TODO)") },
                leadingIcon = { Icon(Icons.Default.Image, contentDescription = null) }
            )

            Text("프로필 공개 여부", fontWeight = FontWeight.SemiBold)
            Row(verticalAlignment = Alignment.CenterVertically) {
                RadioButton(selected = isPublic, onClick = { isPublic = true })
                Text("공개")
                Spacer(Modifier.width(16.dp))
                RadioButton(selected = !isPublic, onClick = { isPublic = false })
                Text("비공개")
            }

            Spacer(Modifier.height(10.dp))

            Button(
                onClick = {
                    scope.launch {
                        prefs.saveProfile(
                            MenteeProfile(
                                name = name.trim(),
                                bio = bio.trim(),
                                isPublic = isPublic,
                                photoUri = ""
                            )
                        )
                        onDone()
                    }
                },
                enabled = name.isNotBlank(),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("저장하고 매칭 화면으로")
            }
        }
    }
}

// -----------------------------
// Match Screen
// -----------------------------
private enum class SwipeDir { LEFT, RIGHT, UP, DOWN, NONE }

private class MatchState(allCourses: List<Course>) {
    private val upcoming = ArrayDeque(allCourses)
    private val past = ArrayDeque<Course>()
    private val future = ArrayDeque<Course>()

    // ✅ Compose state로 변경: next/prev 시 화면이 안정적으로 갱신됨
    var current: Course? by mutableStateOf(
        if (upcoming.isNotEmpty()) upcoming.removeFirst() else null
    )
        private set

    val seenIds = mutableSetOf<String>()

    fun next() {
        val cur = current ?: return
        seenIds.add(cur.id)
        past.addLast(cur)

        current = if (future.isNotEmpty()) {
            future.removeFirst()
        } else {
            var next: Course? = null
            while (upcoming.isNotEmpty() && next == null) {
                val c = upcoming.removeFirst()
                if (!seenIds.contains(c.id)) next = c
            }
            next
        }
    }

    fun prev() {
        val cur = current ?: return
        if (past.isEmpty()) return
        future.addFirst(cur)
        current = past.removeLast()
    }

    fun refresh(allCourses: List<Course>) {
        past.clear()
        future.clear()
        upcoming.clear()
        seenIds.clear()
        allCourses.forEach { upcoming.addLast(it) }
        current = if (upcoming.isNotEmpty()) upcoming.removeFirst() else null
    }
}
private enum class CubeFace { FRONT, TOP, BOTTOM }
@Composable
private fun MatchScreen(
    prefs: MenteePrefs,
    repo: CourseRepository,
    onGoSearch: () -> Unit,
    onGoMyCourses: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val density = LocalDensity.current.density

    val profile by prefs.profileFlow.collectAsState(
        initial = MenteeProfile("", "", true, "")
    )

    var allCourses by remember { mutableStateOf<List<Course>>(emptyList()) }
    var matchState by remember { mutableStateOf<MatchState?>(null) }

    // ✅ 큐브의 "현재 앞면" 상태
    var face by remember { mutableStateOf(CubeFace.FRONT) }

    // ✅ 회전 애니메이션 값
    val rotX = remember { Animatable(0f) }
    val rotY = remember { Animatable(0f) }
    var isAnimating by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        val loaded = repo.loadAllCourses()
        allCourses = loaded
        matchState = MatchState(loaded)
    }

    val cur = matchState?.current

    fun decideDir(dx: Float, dy: Float, threshold: Float = 140f): SwipeDir {
        val adx = abs(dx)
        val ady = abs(dy)
        if (adx < threshold && ady < threshold) return SwipeDir.NONE
        return if (adx > ady) {
            if (dx < 0) SwipeDir.LEFT else SwipeDir.RIGHT
        } else {
            if (dy < 0) SwipeDir.UP else SwipeDir.DOWN
        }
    }

    suspend fun rotateHorizontal(next: Boolean) {
        if (isAnimating) return
        if (face != CubeFace.FRONT) return // 프로필/상세가 열려있으면 좌우 회전 막기
        if (matchState == null) return

        isAnimating = true
        val first = if (next) -90f else 90f
        val second = -first

        rotY.animateTo(first, tween(220, easing = FastOutSlowInEasing))

        // ✅ 반 바퀴 돌았을 때 콘텐츠 교체
        if (next) matchState?.next() else matchState?.prev()

        // ✅ 반대쪽에서 다시 들어오는 느낌
        rotY.snapTo(second)
        rotY.animateTo(0f, tween(220, easing = FastOutSlowInEasing))
        isAnimating = false
    }

    suspend fun openTopProfile() {
        if (isAnimating) return
        if (face != CubeFace.FRONT) return

        isAnimating = true
        rotX.animateTo(-90f, tween(220, easing = FastOutSlowInEasing))
        face = CubeFace.TOP
        rotX.snapTo(90f)
        rotX.animateTo(0f, tween(220, easing = FastOutSlowInEasing))
        isAnimating = false
    }

    suspend fun closeTopProfile() {
        if (isAnimating) return
        if (face != CubeFace.TOP) return

        isAnimating = true
        rotX.animateTo(90f, tween(220, easing = FastOutSlowInEasing))
        face = CubeFace.FRONT
        rotX.snapTo(-90f)
        rotX.animateTo(0f, tween(220, easing = FastOutSlowInEasing))
        isAnimating = false
    }

    suspend fun openBottomDetail() {
        if (isAnimating) return
        if (face != CubeFace.FRONT) return
        if (cur == null) return

        isAnimating = true
        rotX.animateTo(90f, tween(220, easing = FastOutSlowInEasing))
        face = CubeFace.BOTTOM
        rotX.snapTo(-90f)
        rotX.animateTo(0f, tween(220, easing = FastOutSlowInEasing))
        isAnimating = false
    }

    suspend fun closeBottomDetail() {
        if (isAnimating) return
        if (face != CubeFace.BOTTOM) return

        isAnimating = true
        rotX.animateTo(-90f, tween(220, easing = FastOutSlowInEasing))
        face = CubeFace.FRONT
        rotX.snapTo(90f)
        rotX.animateTo(0f, tween(220, easing = FastOutSlowInEasing))
        isAnimating = false
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("매칭") },
                actions = {
                    IconButton(onClick = { onGoMyCourses() }) {
                        Icon(Icons.Default.GridView, contentDescription = "내 강좌")
                    }
                    IconButton(onClick = { onGoSearch() }) {
                        Icon(Icons.Default.Search, contentDescription = "검색")
                    }
                    IconButton(onClick = {
                        matchState?.refresh(allCourses)
                        face = CubeFace.FRONT
                        scope.launch { rotX.snapTo(0f); rotY.snapTo(0f) }
                    }) {
                        Icon(Icons.Default.Refresh, contentDescription = "새로고침")
                    }
                }
            )
        }
    ) { pad ->
        // ✅ 드래그 누적값을 state로 두지 않아서 프레임 안정
        Box(
            Modifier
                .padding(pad)
                .fillMaxSize()
                .padding(16.dp)
                .pointerInput(face, cur?.id, isAnimating) {
                    var totalDx = 0f
                    var totalDy = 0f

                    detectDragGestures(
                        onDragStart = {
                            totalDx = 0f
                            totalDy = 0f
                        },
                        onDrag = { change, dragAmount ->
                            // 지금 버전에서 change.consume()가 잘 되니까 유지
                            change.consume()
                            totalDx += dragAmount.x
                            totalDy += dragAmount.y
                        },
                        onDragEnd = {
                            val dir = decideDir(totalDx, totalDy)

                            scope.launch {
                                when (dir) {
                                    SwipeDir.LEFT -> rotateHorizontal(next = true)
                                    SwipeDir.RIGHT -> rotateHorizontal(next = false)

                                    SwipeDir.DOWN -> {
                                        // ✅ 상세가 열려있으면 닫기, 아니면 프로필 열기
                                        if (face == CubeFace.BOTTOM) closeBottomDetail()
                                        else if (face == CubeFace.FRONT) openTopProfile()
                                    }

                                    SwipeDir.UP -> {
                                        // ✅ 프로필이 열려있으면 닫기, 아니면 상세 열기
                                        if (face == CubeFace.TOP) closeTopProfile()
                                        else if (face == CubeFace.FRONT) openBottomDetail()
                                    }

                                    SwipeDir.NONE -> Unit
                                }
                            }

                            totalDx = 0f
                            totalDy = 0f
                        }
                    )
                },
            contentAlignment = Alignment.Center
        ) {
            // ✅ 큐브 "앞면"이 회전하는 느낌의 컨테이너
            Surface(
                tonalElevation = 6.dp,
                shape = RoundedCornerShape(22.dp),
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(460.dp)
                    .graphicsLayer {
                        transformOrigin = TransformOrigin(0.5f, 0.5f)
                        rotationX = rotX.value
                        rotationY = rotY.value
                        cameraDistance = 24f * density // 3D 원근감
                    }
            ) {
                when (face) {
                    CubeFace.FRONT -> {
                        if (cur == null) {
                            EmptyRecommendationCard(onRefresh = { matchState?.refresh(allCourses) })
                        } else {
                            CourseSwipeCard(
                                course = cur,
                                onApply = {
                                    scope.launch {
                                        prefs.setMatchedCourse(cur.id)
                                        prefs.addMyCourseId(cur.id)
                                        onGoMyCourses()
                                    }
                                },
                                onShowDetail = {
                                    scope.launch { openBottomDetail() } // 버튼 눌러도 "아랫면"으로
                                }
                            )
                        }
                    }

                    CubeFace.TOP -> {
                        ProfileCubeFace(profile = profile)
                    }

                    CubeFace.BOTTOM -> {
                        // BOTTOM 면은 "현재 카드 상세"를 보여줌
                        if (cur == null) {
                            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                Text("상세를 볼 강좌가 없어요.")
                            }
                        } else {
                            DetailCubeFace(course = cur)
                        }
                    }
                }
            }

            // 하단 안내 (상태에 따라 문구 변경)
            Box(
                Modifier
                    .align(Alignment.BottomCenter)
                    .padding(12.dp)
            ) {
                val hint = when (face) {
                    CubeFace.FRONT -> "좌/우: 이전·다음(큐브 회전) · 위: 상세(아랫면) · 아래: 내 프로필(윗면)"
                    CubeFace.TOP -> "위로 스와이프하면 프로필이 닫혀요 (앞면으로 복귀)"
                    CubeFace.BOTTOM -> "아래로 스와이프하면 상세가 닫혀요 (앞면으로 복귀)"
                }
                AssistChip(onClick = { }, label = { Text(hint) })
            }
        }
    }
}


@Composable
private fun CourseSwipeCard(
    course: Course,
    onApply: () -> Unit,
    onShowDetail: () -> Unit
) {
    Surface(
        tonalElevation = 4.dp,
        shape = RoundedCornerShape(22.dp),
        modifier = Modifier
            .fillMaxWidth()
            .height(420.dp)
    ) {
        Column(
            Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(54.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.primaryContainer),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = course.mentorDisplayName.take(1),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                }
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(course.mentorDisplayName, fontWeight = FontWeight.SemiBold)
                    Text(course.summary, style = MaterialTheme.typography.bodySmall)
                }
            }

            Text(
                course.title,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                course.tags.take(3).forEach { tag ->
                    AssistChip(onClick = {}, label = { Text("#$tag") })
                }
            }

            Spacer(Modifier.height(8.dp))

            Text(
                text = "아래에서 위로 스와이프하거나 ‘상세보기’로 세부 정보를 확인할 수 있어요.",
                style = MaterialTheme.typography.bodyMedium
            )

            Spacer(Modifier.weight(1f))

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                OutlinedButton(onClick = onShowDetail, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.Info, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("상세보기")
                }
                Button(onClick = onApply, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.Favorite, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("매칭/신청")
                }
            }
        }
    }
}

@Composable
private fun CourseDetailContent(course: Course) {
    Column(
        Modifier.padding(horizontal = 18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text(course.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text("멘토: ${course.mentorDisplayName}", fontWeight = FontWeight.SemiBold)
        Text(course.detail)
        Text("태그", fontWeight = FontWeight.SemiBold)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            course.tags.forEach { AssistChip(onClick = {}, label = { Text("#$it") }) }
        }
        HorizontalDivider()
        Text(
            "API 연동 예정 필드(빈칸): 가격/일정/정원/리뷰/커리큘럼 등",
            style = MaterialTheme.typography.bodySmall
        )
    }
}

@Composable
private fun EmptyRecommendationCard(onRefresh: () -> Unit) {
    Surface(
        tonalElevation = 2.dp,
        shape = RoundedCornerShape(22.dp),
        modifier = Modifier
            .fillMaxWidth()
            .height(320.dp)
    ) {
        Column(
            Modifier.padding(18.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(Icons.Default.Inbox, contentDescription = null, modifier = Modifier.size(48.dp))
            Spacer(Modifier.height(10.dp))
            Text("더 이상 보여줄 강좌가 없어요.")
            Spacer(Modifier.height(10.dp))
            Button(onClick = onRefresh) { Text("새로고침(전체 다시 보기)") }
        }
    }
}

// -----------------------------
// Search Screen
// -----------------------------
@Composable
private fun SearchScreen(
    repo: CourseRepository,
    onBack: () -> Unit
) {
    var all by remember { mutableStateOf<List<Course>>(emptyList()) }
    var q by remember { mutableStateOf("") }

    LaunchedEffect(Unit) { all = repo.loadAllCourses() }

    val filtered = remember(q, all) {
        val key = q.trim()
        if (key.isBlank()) all
        else all.filter { it.title.contains(key, true) || it.mentorDisplayName.contains(key, true) }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("검색") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "뒤로")
                    }
                }
            )
        }
    ) { pad ->
        Column(
            Modifier
                .padding(pad)
                .fillMaxSize()
                .padding(16.dp)
        ) {
            OutlinedTextField(
                value = q,
                onValueChange = { q = it },
                label = { Text("강좌/멘토 검색") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(12.dp))

            if (filtered.isEmpty()) {
                Text("검색 결과 없음")
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    filtered.take(20).forEach { c ->
                        Surface(tonalElevation = 1.dp, shape = RoundedCornerShape(14.dp)) {
                            Column(Modifier.padding(14.dp)) {
                                Text(c.title, fontWeight = FontWeight.SemiBold)
                                Text(
                                    "${c.mentorDisplayName} · ${c.summary}",
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                        }
                    }
                }
            }

            Spacer(Modifier.height(10.dp))
            Text("※ 실제 검색은 API/필터 조건 붙일 예정", style = MaterialTheme.typography.bodySmall)
        }
    }
}

// -----------------------------
// My Courses Screen
// -----------------------------
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun MyCoursesScreen(
    prefs: MenteePrefs,
    repo: CourseRepository,
    onBack: () -> Unit,
    onGoMatch: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var all by remember { mutableStateOf<List<Course>>(emptyList()) }

    var orderedIds by remember { mutableStateOf<List<String>>(emptyList()) }
    var items by remember { mutableStateOf<List<Course>>(emptyList()) }

    var draggingId by remember { mutableStateOf<String?>(null) }
    var dragOffset by remember { mutableStateOf(Offset.Zero) }
    val boundsMap = remember { mutableStateMapOf<String, Rect>() }

    LaunchedEffect(Unit) {
        all = repo.loadAllCourses()
        orderedIds = prefs.getMyCourseIds()

        if (orderedIds.isEmpty() && all.isNotEmpty()) {
            orderedIds = all.take(3).map { it.id }
            prefs.setMyCourseIds(orderedIds)
        }
        items = orderedIds.mapNotNull { id -> all.find { it.id == id } }
    }

    fun persistOrder(newList: List<Course>) {
        scope.launch {
            prefs.setMyCourseIds(newList.map { it.id })
        }
    }

    fun swapByTarget(dragId: String, center: Offset) {
        val target = boundsMap.entries.firstOrNull { (_, rect) -> rect.contains(center) }?.key
        if (target != null && target != dragId) {
            val cur = items.toMutableList()
            val from = cur.indexOfFirst { it.id == dragId }
            val to = cur.indexOfFirst { it.id == target }
            if (from != -1 && to != -1) {
                val tmp = cur[from]
                cur[from] = cur[to]
                cur[to] = tmp
                items = cur
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("내 강좌") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "뒤로")
                    }
                },
                actions = {
                    IconButton(onClick = onGoMatch) {
                        Icon(Icons.Default.Swipe, contentDescription = "매칭으로")
                    }
                }
            )
        }
    ) { pad ->
        Column(
            Modifier
                .padding(pad)
                .fillMaxSize()
                .padding(12.dp)
        ) {
            Text("롱프레스 후 드래그해서 아이콘 순서를 바꿀 수 있어요.", style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(10.dp))

            LazyVerticalGrid(
                columns = GridCells.Fixed(3),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize()
            ) {
                items(items, key = { it.id }) { course ->
                    val isDragging = draggingId == course.id

                    Surface(
                        tonalElevation = if (isDragging) 6.dp else 1.dp,
                        shape = RoundedCornerShape(18.dp),
                        modifier = Modifier
                            .aspectRatio(1f)
                            .onGloballyPositioned { coords ->
                                boundsMap[course.id] = coords.boundsInRoot()
                            }
                            .graphicsLayer {
                                if (isDragging) {
                                    translationX = dragOffset.x
                                    translationY = dragOffset.y
                                    scaleX = 1.05f
                                    scaleY = 1.05f
                                }
                            }
                            .pointerInput(course.id) {
                                detectDragGesturesAfterLongPress(
                                    onDragStart = {
                                        draggingId = course.id
                                        dragOffset = Offset.Zero
                                    },
                                    onDrag = { change, amount ->
                                        change.consume()
                                        val id = draggingId ?: return@detectDragGesturesAfterLongPress
                                        dragOffset += amount

                                        val rect = boundsMap[id] ?: return@detectDragGesturesAfterLongPress
                                        val center = rect.center + dragOffset
                                        swapByTarget(id, center)
                                    },
                                    onDragEnd = {
                                        draggingId = null
                                        dragOffset = Offset.Zero
                                        persistOrder(items)
                                    },
                                    onDragCancel = {
                                        draggingId = null
                                        dragOffset = Offset.Zero
                                    }
                                )
                            }
                    ) {
                        Column(
                            Modifier
                                .fillMaxSize()
                                .padding(12.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.Center
                        ) {
                            Box(
                                Modifier
                                    .size(46.dp)
                                    .clip(CircleShape)
                                    .background(MaterialTheme.colorScheme.secondaryContainer),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(course.mentorDisplayName.take(1), fontWeight = FontWeight.Bold)
                            }
                            Spacer(Modifier.height(10.dp))
                            Text(
                                course.title,
                                maxLines = 2,
                                style = MaterialTheme.typography.bodySmall,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ProfileCubeFace(profile: MenteeProfile) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Person, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("내 프로필 (큐브 윗면)", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        }

        Surface(
            shape = RoundedCornerShape(18.dp),
            tonalElevation = 2.dp,
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("이름: ${profile.name.ifBlank { "(미입력)" }}", fontWeight = FontWeight.SemiBold)
                Text("소개: ${profile.bio.ifBlank { "(없음)" }}")
                Text("공개여부: ${if (profile.isPublic) "공개" else "비공개"}")
            }
        }

        Spacer(Modifier.weight(1f))

        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.KeyboardDoubleArrowUp, contentDescription = null)
            Spacer(Modifier.width(6.dp))
            Text("위로 스와이프하면 닫혀요", style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun DetailCubeFace(course: Course) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Info, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("상세 (큐브 아랫면)", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        }

        Surface(
            shape = RoundedCornerShape(18.dp),
            tonalElevation = 2.dp,
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(course.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text("멘토: ${course.mentorDisplayName}", fontWeight = FontWeight.SemiBold)
                Text(course.detail)

                Text("태그", fontWeight = FontWeight.SemiBold)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    course.tags.forEach { AssistChip(onClick = {}, label = { Text("#$it") }) }
                }

                HorizontalDivider()
                Text(
                    "API 연동 예정 필드(빈칸): 가격/일정/정원/리뷰/커리큘럼 등",
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }

        Spacer(Modifier.weight(1f))

        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.KeyboardDoubleArrowDown, contentDescription = null)
            Spacer(Modifier.width(6.dp))
            Text("아래로 스와이프하면 닫혀요", style = MaterialTheme.typography.bodyMedium)
        }
    }
}
