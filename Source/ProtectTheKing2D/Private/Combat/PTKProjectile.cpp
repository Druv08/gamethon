// Protect the King - 2D. The one reusable projectile.

#include "Combat/PTKProjectile.h"

#include "Combat/PTKCombatTarget.h"
#include "Components/PTKHealthComponent.h"
#include "Components/SphereComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/OverlapResult.h"
#include "Engine/World.h"
#include "PaperFlipbook.h"
#include "PaperFlipbookComponent.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKProjectile)

APTKProjectile::APTKProjectile()
{
	PrimaryActorTick.bCanEverTick = true;

	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	SetRootComponent(Collision);
	Collision->InitSphereRadius(CollisionRadius);
	// The sweep in Tick is what finds victims, so the component itself needs no
	// collision response at all. Leaving it queryable would let an arrow shove
	// the archer who fired it.
	Collision->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Collision->SetGenerateOverlapEvents(false);

	Sprite = CreateDefaultSubobject<UPaperFlipbookComponent>(TEXT("Sprite"));
	Sprite->SetupAttachment(Collision);
	Sprite->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Sprite->SetGenerateOverlapEvents(false);

	// Sprites in this project render only from -Y, and viewing the XZ plane
	// from there mirrors them. Cancelled on the component exactly as the
	// characters do it - never by moving the camera. See APTKTopDownCharacter.
	Sprite->SetRelativeScale3D(FVector(-1.0f, 1.0f, 1.0f));

	// Flat 2D play plane: an arrow must not drift in depth.
	SetActorEnableCollision(false);
	InitialLifeSpan = 0.0f;
}

void APTKProjectile::BeginPlay()
{
	Super::BeginPlay();
	if (Collision)
	{
		Collision->SetSphereRadius(CollisionRadius);
	}
}

void APTKProjectile::Launch(const FVector& InDirection, EPTKFacingDirection InFacing,
	AActor* InSource, EPTKTeam InOwningTeam, float InDamage,
	float InSpeed, float InRange, float InVisualHeight, const FVector& InUpVector)
{
	Direction = InDirection.GetSafeNormal();
	if (Direction.IsNearlyZero())
	{
		UE_LOG(LogPTK, Warning,
			TEXT("PROJECTILE | %s launched with no direction - destroyed"), *GetName());
		Destroy();
		return;
	}

	SourceActor = InSource;
	OwningTeam = InOwningTeam;
	Damage = InDamage;
	Speed = InSpeed;
	MaxRange = InRange;
	DistanceTravelled = 0.0f;
	TimeAlive = 0.0f;
	bSpent = false;
	bLaunched = true;

	// Visual only. The actor stays on the shooter's own row so that what the
	// sweep tests and what the player sees crossing an enemy are the same
	// thing - see the class comment, this is what the misses were.
	VisualHeightOffset = InVisualHeight;
	UpVector = InUpVector.GetSafeNormal();
	if (UpVector.IsNearlyZero())
	{
		UpVector = FVector(0.0f, 0.0f, 1.0f);
	}

	// Perpendicular part only - see VisualOffset. This is what keeps what the
	// sweep tests and what the player sees on the same line.
	VisualOffset = UpVector * VisualHeightOffset;
	VisualOffset -= Direction * FVector::DotProduct(VisualOffset, Direction);

	if (Sprite)
	{
		Sprite->SetWorldLocation(GetActorLocation() + VisualOffset);
		if (UPaperFlipbook* const Flight = FlightFlipbooks.GetForDirection(InFacing))
		{
			Sprite->SetFlipbook(Flight);
			Sprite->SetLooping(true);
			Sprite->PlayFromStart();
		}
		else
		{
			UE_LOG(LogPTK, Warning,
				TEXT("PROJECTILE | %s has no flight flipbook for %s - it will fly invisibly"),
				*GetName(), *UPTKTypesLibrary::DirectionToString(InFacing));
		}
	}

	UE_LOG(LogPTK, Log,
		TEXT("PROJECTILE FIRED | %s | from: %s | dir: %s (%s) | damage: %.1f | speed: %.0f | range: %.0f"),
		*GetName(), SourceActor ? *SourceActor->GetName() : TEXT("none"),
		*UPTKTypesLibrary::DirectionToString(InFacing), *Direction.ToCompactString(),
		Damage, Speed, MaxRange);
}

void APTKProjectile::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (!bLaunched || bSpent)
	{
		return;
	}

	TimeAlive += DeltaSeconds;
	if (TimeAlive >= MaxLifetime)
	{
		Expire(nullptr, GetActorLocation());
		return;
	}

	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	const FVector Start = GetActorLocation();
	float Step = Speed * DeltaSeconds;

	// Never travel further than the stated range, even on a long frame: the
	// last step is trimmed so the arrow stops exactly at its reach rather than
	// overshooting it by however much the frame happened to be worth.
	const float Remaining = MaxRange - DistanceTravelled;
	bool bReachedRange = false;
	if (Step >= Remaining)
	{
		Step = Remaining;
		bReachedRange = true;
	}

	const FVector End = Start + Direction * Step;

	// A sweep, not an overlap at the destination. At 900 uu/s an arrow covers
	// 15 units a frame at 60fps and far more on a slow one - a point test would
	// step straight over a body between frames.
	TArray<FHitResult> Hits;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(PTKProjectileFlight), false, this);
	Params.AddIgnoredActor(this);
	if (SourceActor)
	{
		Params.AddIgnoredActor(SourceActor);
	}

	World->SweepMultiByObjectType(
		Hits, Start, End, FQuat::Identity,
		FCollisionObjectQueryParams(ECC_Pawn),
		FCollisionShape::MakeSphere(CollisionRadius), Params);

	if (bDrawFlight)
	{
		DrawDebugLine(World, Start, End, FColor::Cyan, false, 0.5f, 0, 1.0f);
	}

	// Hits come back in order along the sweep, so the first hostile one is the
	// nearest - which is the enemy the arrow would really have struck first.
	// It decides only WHERE the arrow stops; ApplySplash decides who is hurt.
	for (const FHitResult& Hit : Hits)
	{
		AActor* const Victim = Hit.GetActor();
		if (bTargetRestricted && Victim != IntendedTarget.Get()) continue;
		if (Victim == SourceActor || !PTKCombat::IsEngageable(Victim))
		{
			continue;
		}

		// The shared hostility rule, not a local team comparison. Guards and
		// the King are different teams but the same side, so this is what
		// stops a guard's arrow from killing the man he is defending.
		const IPTKCombatTarget* const Target = PTKCombat::From(Victim);
		if (!Target || !PTKCombat::AreHostile(OwningTeam, Target->GetCombatTeam()))
		{
			continue;
		}

		// Spent whether or not damage lands. An arrow that strikes an enemy
		// already at zero has still struck it, and must not sail on to hit
		// somebody behind - that would be a piercing arrow, which is a later
		// ability and not this one.
		Expire(Victim, Hit.ImpactPoint);
		return;
	}

	SetActorLocation(End, false);
	DistanceTravelled += Step;
	if (Sprite)
	{
		Sprite->SetWorldLocation(End + VisualOffset);
	}

	if (bReachedRange)
	{
		UE_LOG(LogPTK, Log,
			TEXT("PROJECTILE EXPIRED | %s | reached %.0f uu without hitting anything"),
			*GetName(), MaxRange);
		Expire(nullptr, End);
	}
}

int32 APTKProjectile::ApplySplash(const FVector& AtLocation, AActor* DirectVictim)
{
	UWorld* const World = GetWorld();
	if (!World || Damage <= 0.0f)
	{
		return 0;
	}

	// Strictly single target. Damaging only what was struck is not the same as
	// overlapping a tiny sphere: an 18-unit enemy capsule pressed against
	// another would be caught by any radius at all, so a spell that is supposed
	// to hit one body has to skip the query entirely.
	if (SplashRadius <= 0.0f || bTargetRestricted)
	{
		if (!PTKCombat::IsEngageable(DirectVictim))
		{
			return 0;
		}
		float Direct = 0.0f;
		if (UPTKHealthComponent* const Health = PTKCombat::GetHealth(DirectVictim))
		{
			Direct = Health->ApplyDamage(Damage, SourceActor ? SourceActor : this);
		}
		UE_LOG(LogPTK, Log,
			TEXT("PROJECTILE HIT | %s -> %s | damage: %.1f | travelled: %.0f of %.0f | single target"),
			*GetName(), *DirectVictim->GetName(), Direct, DistanceTravelled, MaxRange);
		if (Direct > 0.0f)
		{
			OnProjectileHit(DirectVictim, Direct);
		}
		return 1;
	}

	// A radius of zero still has to damage what the arrow physically struck, so
	// the overlap always runs - it is simply tight enough to catch only that
	// body. Single-target and splash therefore share ONE code path, and the
	// once-per-enemy rule below cannot be true of one and not the other.
	const float Radius = FMath::Max(SplashRadius, CollisionRadius);

	TArray<FOverlapResult> Overlaps;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(PTKProjectileSplash), false, this);
	Params.AddIgnoredActor(this);
	if (SourceActor)
	{
		Params.AddIgnoredActor(SourceActor);
	}

	World->OverlapMultiByObjectType(
		Overlaps, AtLocation, FQuat::Identity,
		FCollisionObjectQueryParams(ECC_Pawn),
		FCollisionShape::MakeSphere(Radius), Params);

	if (bDrawFlight)
	{
		DrawDebugSphere(World, AtLocation, Radius, 16, FColor::Cyan, false, 1.0f);
	}

	// One arrow damages one enemy once, however the blast overlaps it. The set
	// is what guarantees that, not the shape of the query.
	TSet<AActor*> Struck;
	int32 Count = 0;
	for (const FOverlapResult& Result : Overlaps)
	{
		AActor* const Victim = Result.GetActor();
		if (Victim == SourceActor || !PTKCombat::IsEngageable(Victim))
		{
			continue;
		}
		const IPTKCombatTarget* const Target = PTKCombat::From(Victim);
		if (!Target || !PTKCombat::AreHostile(OwningTeam, Target->GetCombatTeam()))
		{
			continue;
		}
		bool bAlready = false;
		Struck.Add(Victim, &bAlready);
		if (bAlready)
		{
			continue;
		}

		float Dealt = 0.0f;
		if (UPTKHealthComponent* const Health = PTKCombat::GetHealth(Victim))
		{
			Dealt = Health->ApplyDamage(Damage, SourceActor ? SourceActor : this);
		}
		++Count;

		// The distance is logged so the blast radius can be checked rather than
		// trusted: every victim must be inside it, and anything further away
		// must be absent from this list entirely.
		UE_LOG(LogPTK, Log,
			TEXT("PROJECTILE HIT | %s -> %s | damage: %.1f | dist: %.0f of %.0f | ")
			TEXT("travelled: %.0f of %.0f"),
			*GetName(), *Victim->GetName(), Dealt,
			FVector::Dist(AtLocation, Victim->GetActorLocation()), Radius,
			DistanceTravelled, MaxRange);

		if (Dealt > 0.0f)
		{
			OnProjectileHit(Victim, Dealt);
		}
	}

	UE_LOG(LogPTK, Log, TEXT("PROJECTILE BURST | %s | %d enemies caught within %.0f uu"),
		*GetName(), Count, Radius);
	return Count;
}

void APTKProjectile::Expire(AActor* DirectVictim, const FVector& AtLocation)
{
	if (bSpent)
	{
		return;
	}
	bSpent = true;
	SetActorLocation(AtLocation, false);

	if (DirectVictim)
	{
		ApplySplash(AtLocation, DirectVictim);
	}

	if (Sprite)
	{
		// Drawn where the arrow VISUALLY was, which is the same line it was
		// swept along - the burst must not drop to the feet after a shot the
		// player watched cross at bow height.
		Sprite->SetWorldLocation(AtLocation + VisualOffset);
	}

	if (Sprite && ImpactFlipbook)
	{
		Sprite->SetFlipbook(ImpactFlipbook);
		Sprite->SetLooping(false);
		Sprite->PlayFromStart();
		SetLifeSpan(FMath::Max(ImpactLifetime, 0.01f));
		UE_LOG(LogPTK, Log,
			TEXT("PROJECTILE IMPACT | %s | burst '%s' playing for %.2fs at %s"),
			*GetName(), *ImpactFlipbook->GetName(), ImpactLifetime,
			*AtLocation.ToCompactString());
		return;
	}

	// No burst art assigned: go quietly rather than leaving a frozen arrow
	// hanging in the air.
	Destroy();
}
